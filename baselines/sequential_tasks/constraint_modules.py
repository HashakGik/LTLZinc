import torch
import torch.nn.functional as F
import scallopy

class ConstraintMLP(torch.nn.Module):
    def __init__(self, num_neurons, num_classes, propositions, calibrate, eps):
        super().__init__()

        self.propositions = propositions
        self.calibrate = calibrate
        self.eps = eps

        self.temperature_logits = torch.nn.Parameter(torch.ones(len(propositions), requires_grad=True))

        self.net = torch.nn.ModuleDict(
            {p: torch.nn.Sequential(
                torch.nn.Linear(num_classes, num_neurons),
                torch.nn.ReLU(),
                torch.nn.Linear(num_neurons, 1)
            ) for p in propositions})

    def forward(self, imgs):
        input_tensor = torch.cat([imgs[i] for i in sorted(imgs.keys())], dim=1)

        if self.calibrate:
            t = F.relu(self.temperature_logits) + self.eps
            out = {p: F.sigmoid(self.net[p](input_tensor).squeeze(1) / t[i]) for i, p in enumerate(sorted(self.net.keys()))}
        else:
            out = {p: F.sigmoid(self.net[p](input_tensor).squeeze(1)) for p in self.net.keys()}

        return out

class ConstraintScallop(torch.nn.Module):
    def __init__(self, program_path, classes, propositions, provenance, train_k, test_k, calibrate, eps):
        super().__init__()

        domains = {}
        for k, v in classes.items():
            if all([v2.isnumeric() for v2 in v.keys()]):
                domains[k] = [int(v2) for v2 in sorted(v.keys())]  # Map integers to themselves.
            else:
                domains[k] = sorted(v.values())  # Map categoricals to integer idx.

        self.propositions = propositions

        self.net = scallopy.Module(
            file="{}/scallop_constraints.scl".format(program_path),
            input_mappings=domains,
            output_mappings={k: () for k in self.propositions},
            provenance=provenance,
            train_k=train_k,
            test_k=test_k,
            retain_graph=True,
            #early_discard=False,
            )

        self.classes_temp_logits = torch.nn.Parameter(torch.ones(len(classes), requires_grad=True))
        self.props_temp_logits = torch.nn.Parameter(torch.ones(len(propositions), requires_grad=True))
        self.calibrate = calibrate
        self.eps = eps


    def forward(self, imgs):
        if self.calibrate:
            t = F.relu(self.classes_temp_logits) + self.eps
            nesy_in = {k: F.softmax(imgs[k] / t[i], dim=1) for i, k in enumerate(sorted(imgs.keys()))}
        else:
            nesy_in = {k: F.softmax(v, dim=1) for k, v in imgs.items()}

        nesy_out = self.net(**nesy_in)

        # If there is only one output, Scallop returns a tensor, instead of a dict of tensors. Fixing it.
        if not isinstance(nesy_out, dict):
            nesy_out = {self.propositions[0]: nesy_out}

        if self.calibrate:
            t = F.relu(self.props_temp_logits) + self.eps
            nesy_out = {k: torch.sigmoid(torch.logit(nesy_out[k], self.eps) / t[i]) for i, k in enumerate(sorted(nesy_out.keys()))}

        return nesy_out
