# Adversarial training with AugMax for ASR based on robust_speech

This project is based on [robust speech](https://github.com/RaphaelOlivier/robust_speech) led by [Raphael Olivier](https://raphaelolivier.github.io) under the supervision of Prof. Bhiksha Raj.

## Usage
We provide scripts to train and evaluate models (with adversarial attacks in both stages). These scripts are similar to speechbrain training recipes.

We also provide a number of training and evaluation config files ready for use.

Example

```
# in ./recipes/

# This will download the speechbrain/asr-crdnn-rnnlm-librispeech model from huggingface
python evaluate.py attack_configs/augmax/s2s_1000bpe.yaml --root=/path/to/results/folder 

# This will train a model first
python train.py train_configs/seq2seq_augmax.yaml --root=/path/to/results/folder
mv /path/to/training/outputs/folder/*.ckpt /path/to/models/folder/asr-ctcrnn-librispeech/
python evaluate.py attack_configs/augmax/s2s_1000bpe.yaml --root=/path/to/results/folder
```

Our provided configs assume a results folder structure such as
```
root
│
└───data
│   │ # where datasets are dumped (e.g. download LibriSpeech here)
│
└───models
│   │
│   └───model_name1
│   │   │   model.ckpt
│   
└───tokenizers   
│   │ # where all tokenizers are saved
│   
└───trainings
│   │  # where your custom models are trained
│  
└───attacks
|   |
│   └───attack_name
│   │   │
│   │   └───1234 # seed
│   │   │   │
│   │   │   └───model_name1
│   │   │   │   │ # your attack results

```