---
license: apache-2.0
tags:
- generated_from_trainer
metrics:
- wer
model-index:
- name: whisper-tiny-ar-quran
  results: []
---

<!-- This model card has been generated automatically according to the information the Trainer had access to. You
should probably proofread and complete it, then remove this comment. -->

# whisper-tiny-ar-quran

This model is a fine-tuned version of [openai/whisper-tiny](https://huggingface.co/openai/whisper-tiny) on the None dataset.
It achieves the following results on the evaluation set:
- Loss: 0.0928
- Wer: 7.0535

## Model description

More information needed

## Intended uses & limitations

More information needed

## Training and evaluation data

More information needed

## Training procedure

### Training hyperparameters

The following hyperparameters were used during training:
- learning_rate: 0.0001
- train_batch_size: 16
- eval_batch_size: 8
- seed: 42
- optimizer: Adam with betas=(0.9,0.999) and epsilon=1e-08
- lr_scheduler_type: linear
- lr_scheduler_warmup_steps: 500
- training_steps: 5000
- mixed_precision_training: Native AMP

### Training results

| Training Loss | Epoch | Step | Validation Loss | Wer     |
|:-------------:|:-----:|:----:|:---------------:|:-------:|
| 0.1766        | 0.05  | 500  | 0.2829          | 20.0236 |
| 0.1129        | 0.09  | 1000 | 0.1981          | 13.8364 |
| 0.0775        | 0.14  | 1500 | 0.1763          | 12.5450 |
| 0.0678        | 0.19  | 2000 | 0.1485          | 10.7302 |
| 0.0437        | 0.23  | 2500 | 0.1336          | 9.6693  |
| 0.0341        | 0.28  | 3000 | 0.1244          | 8.9602  |
| 0.0302        | 0.33  | 3500 | 0.1059          | 8.2224  |
| 0.0189        | 0.37  | 4000 | 0.1044          | 7.6902  |
| 0.0167        | 0.42  | 4500 | 0.0966          | 7.2643  |
| 0.0151        | 0.47  | 5000 | 0.0928          | 7.0535  |


### Framework versions

- Transformers 4.26.0.dev0
- Pytorch 1.13.0+cu117
- Datasets 2.7.1.dev0
- Tokenizers 0.13.2
