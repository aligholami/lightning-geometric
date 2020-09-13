import os
import os.path as osp
import numpy as np
from functools import partial
from hydra.utils import get_class
from omegaconf import OmegaConf
import torch
from torch.utils.data import DataLoader, random_split
from pytorch_lightning import LightningDataModule
import torch_geometric
from ogb.nodeproppred import Evaluator
import torch_geometric.transforms as T
from torch_geometric.data import NeighborSampler
import pytorch_lightning as pl
from sklearn.metrics import f1_score

from examples.datasets.base_dataset import BaseDataset


class OgbnArxivDataset(BaseDataset):

    NAME = "OgbnArxiv"

    def __init__(
        self,
        dataset=None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, transform=dataset.params.transform, **kwargs)
        assert dataset.params.name == "ogbn-arxiv"
        self._dataset = dataset

    @property
    def num_features(self):
        return 128  # TODO Find a better way to infer it

    @property
    def num_classes(self):
        return 40

    def prepare_data(self):
        path = osp.join(
            osp.dirname(osp.realpath(__file__)), "..", "..", "data", self.NAME
        )

        dataset = OmegaConf.to_container(self._dataset)
        self.evaluator = Evaluator(dataset["params"]["name"])

        dataset["params"]["transform"] = self._transform
        dataset["params"]["root"] = path
        dataset_cls = get_class(dataset["_target_"])

        self.dataset = dataset_cls(**dataset["params"])
        self.split_idx = self.dataset.get_idx_split()
        self.data = self.dataset[0]
        self.data.adj_t = self.data.adj_t.to_symmetric()
        self.data.adj_t.storage._row.long()
        self.data.adj_t.storage._col.long()

    def train_dataloader(self, batch_size=32, transforms=None):
        return NeighborSampler(
            self.data.adj_t[self.split_idx["train"]],
            node_idx=self.split_idx["train"],
            sizes=[-1, 10],
            batch_size=batch_size,
            shuffle=True,
            num_workers=self._num_workers,
        )

    def val_dataloader(self, batch_size=32, transforms=None):
        import pdb

        pdb.set_trace()
        return NeighborSampler(
            self.data.adj_t[self.split_idx["valid"]],
            node_idx=self.split_idx["valid"],
            sizes=[-1, 10],
            batch_size=batch_size,
            shuffle=True,
            num_workers=self._num_workers,
        )

    def test_dataloader(self, batch_size=32, transforms=None):
        return NeighborSampler(
            self.data.adj_t[self.split_idx["test"]],
            node_idx=self.split_idx["test"],
            sizes=[-1, 10],
            batch_size=batch_size,
            shuffle=True,
            num_workers=self._num_workers,
        )

    def training_step(self, batch, batch_nb):
        loss = batch.num_graphs * self.loss_op(
            self.forward(batch.x, batch.edge_index), batch.y
        )
        result = pl.TrainResult(loss)
        result.log("train_loss", loss, prog_bar=True)
        return result

    def validation_step(self, batch, batch_nb):
        preds = self.forward(batch.x, batch.edge_index)
        loss = batch.num_graphs * self.loss_op(preds, batch.y)
        result = pl.EvalResult(loss)
        result.log("val_loss", loss)
        result.y = batch.y
        result.preds = preds
        result.num_graphs = torch.tensor([batch.num_graphs]).float()
        return result

    def validation_epoch_end(self, outputs):
        avg_loss = outputs["val_loss"].sum() / outputs["num_graphs"].sum()
        val_f1_score = torch.tensor(
            [f1_score(outputs["y"], outputs["preds"] > 0, average="micro")]
        )
        result = pl.EvalResult(checkpoint_on=val_f1_score)
        result.log("val_loss", avg_loss, prog_bar=True)
        result.log("val_f1_score", val_f1_score, prog_bar=True)
        return result
