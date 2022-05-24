# Adversarial training with AugMax for ASR based on robust_speech

This project is based on [robust speech](https://github.com/RaphaelOlivier/robust_speech) led by [Raphael Olivier](https://raphaelolivier.github.io) under the supervision of Prof. Bhiksha Raj.

See [video Link](https://youtu.be/20fBSTEkO0w) for a video presentation of our work
See [here](https://drive.google.com/drive/folders/1uRYPP_nYhg-MZ3mkAx2W1GlquiV5aePs?usp=sharing) for some of our generated adversarial samples.

## Usage
```
# Before running code, please download LibriSpeech data in the `root/data` folder 
# in ./recipes/

# Adversarial attack using AugMax
python evaluate.py attack_configs/augmax/s2s_1000bpe.yaml --root=/path/to/results/folder 

# Adversarial training using AugMax
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
