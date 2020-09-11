import os.path as osp

import torch
from torch import nn
import torch.nn.functional as F
from torch_geometric.nn import GATConv
import pytorch_lightning as pl

class GATConvNet(pl.LightningModule):
    def __init__(self, *args, **kwargs):
        super().__init__()

        self.save_hyperparameters()

        self.conv1 = GATConv(kwargs["num_features"], 256, heads=4)
        self.lin1 = torch.nn.Linear(kwargs["num_features"], 4 * 256)
        self.conv2 = GATConv(4 * 256, 256, heads=4)
        self.lin2 = torch.nn.Linear(4 * 256, 4 * 256)
        self.conv3 = GATConv(4 * 256, kwargs["num_classes"], heads=6,
                             concat=False)
        self.lin3 = torch.nn.Linear(4 * 256, kwargs["num_classes"])

    def forward(self, x, edge_index):
        x = F.elu(self.conv1(x, edge_index) + self.lin1(x))
        x = F.elu(self.conv2(x, edge_index) + self.lin2(x))
        x = self.conv3(x, edge_index) + self.lin3(x)
        return x

    def training_step(self, batch, batch_nb):
        loss = F.nll_loss(F.log_softmax(self.forward(batch.x, batch.edge_index), -1), batch.y)
        result = pl.TrainResult(loss)
        result.log('train_loss', loss)
        return result

    def configure_optimizers(self):
        return torch.optim.Adam(self.parameters(), lr=0.02)