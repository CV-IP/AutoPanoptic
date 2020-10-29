# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved.
import torch
import torchvision

from maskrcnn_benchmark.structures.bounding_box import BoxList
from maskrcnn_benchmark.structures.segmentation_mask import SegmentationMask
from PIL import Image
import numpy as np


class COCODataset(torchvision.datasets.coco.CocoDetection):
    def __init__(
        self, ann_file, seg_ann_file, root, remove_images_without_annotations, transforms=None
    ):
        super(COCODataset, self).__init__(root, ann_file)
        # sort indices for reproducible results
        self.ids = sorted(self.ids)
        # filter images without detection annotations
        self.seg_ann_file = seg_ann_file

        if remove_images_without_annotations:
            self.ids = [
                img_id
                for img_id in self.ids
                if len(self.coco.getAnnIds(imgIds=img_id, iscrowd=None)) > 0
            ]

            ids_to_remove = []
            for img_id in self.ids:
                ann_ids = self.coco.getAnnIds(imgIds=img_id)
                anno = self.coco.loadAnns(ann_ids)
                if all(
                    any(o <= 1 for o in obj["bbox"][2:])
                    for obj in anno
                    if obj["iscrowd"] == 0
                ):
                    ids_to_remove.append(img_id)

            self.ids = [
                img_id for img_id in self.ids if img_id not in ids_to_remove
            ]

        self.json_category_id_to_contiguous_id = {
            v: i + 1 for i, v in enumerate(self.coco.getCatIds())
        }
        self.contiguous_category_id_to_json_id = {
            v: k for k, v in self.json_category_id_to_contiguous_id.items()
        }
        self.id_to_img_map = {k: v for k, v in enumerate(self.ids)} # img_map is not continuous

        self.transforms = transforms

    def __getitem__(self, idx):
        img, anno = super(COCODataset, self).__getitem__(idx) # anno: [{'segmentation': [[]], 'area': double, 'iscrowd': T/F, 'image_id': int, 'bbox': [], 'category_id': int, 'id': int},{}, ... , {}]
        # filter crowd annotations
        # TODO might be better to add an extra field
        
        origin_size = (img.size[1], img.size[0]) # width x height!!! -> height x width
        # return orignal size for semantic segmentation
        anno = [obj for obj in anno if obj["iscrowd"] == 0]

        boxes = [obj["bbox"] for obj in anno]
        boxes = torch.as_tensor(boxes).reshape(-1, 4)  # guard against no boxes
        target = BoxList(boxes, img.size, mode="xywh").convert("xyxy")

        classes = [obj["category_id"] for obj in anno]
        classes = [self.json_category_id_to_contiguous_id[c] for c in classes]
        classes = torch.tensor(classes)
        target.add_field("labels", classes)

        masks = [obj["segmentation"] for obj in anno]
        masks = SegmentationMask(masks, img.size)
        target.add_field("masks", masks)

        if 'ADE' in self.seg_ann_file:
            img_id = self.id_to_img_map[idx]
            img_fname = self.seg_ann_file + '/' + str(img_id).rjust(8,'0') + '.png'
        else:
            img_id = self.id_to_img_map[idx]
            img_fname = self.seg_ann_file + '/' + str(img_id).rjust(12,'0') + '.png'
        segment = Image.open(img_fname)

        target = target.clip_to_image(remove_empty=True)

        if self.transforms is not None:
            img, target, segment = self.transforms(img, target, segment) # img: Tensor, target: BoxList

        return img, target, segment, idx, img_id, origin_size

    def get_img_info(self, index):
        img_id = self.id_to_img_map[index]
        img_data = self.coco.imgs[img_id]
        return img_data
