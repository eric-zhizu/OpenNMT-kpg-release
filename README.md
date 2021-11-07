# Neural Keyphrase Generation

Welcome to our neural keyphrase generation repository! The goal of this project is to use language models to generate abstractive keyphrases that summarize an article.

Please follow these steps to train or evaluate our models.

# Launch an AWS cloud GPU instance

This codebase requires that the machine has access to CUDA-compatible GPUs developed by NVIDIA. You can access such machines on AWS.

We assume you know how to launch an instanec on AWS. Here are a few things to keep in mind:

- Select the latest Deep Learning AMI.
- Select either a g4dn or a p3 instance. Note that p3 instances are faster but more expensive.

# Download the data

Clone this repository using `git clone`.

Take a look at the data in this Google Drive folder. https://drive.google.com/drive/folders/1nJL-LC0M8lXdDEl0ZRQMc_rcuvvKO5Hb

Download the data from Google Drive into the home directory `~` of your AWS instance. There are many ways to do this. One way is to use the command-line tool `gdown`, which you might have to `pip install`. Then use the `unzip` command to unzip the files.

There are three important files which you should download:
- data.zip : contains the articles and their keywords
- magkp20k.vocab.json : contains a mapping from vocab words to their frequency in the corpus
- models.zip : contains pre-trained models

# Install the appropriate packages

Activate the conda environment `conda activate pytorch_p37`.

In the command line, run `python setup.py install`.

Also run `python -m spacy download 'en_core_web_sm'`.

# Run the training/evaluation scripts

## Train
Training scripts are stored in `script/empirical_study/diverse/rnn` or `script/empirical_study/diverse/transformer`. When you run a script using the `bash` interpreter, make sure to alter the `.sh` files so that `train.py` is invoked with the right parameters. For example, make sure the output directory points to an existing folder on your machine.

## Evaluate
We put the evaluation script in `script/empirical_study/diverse/kpeval_gpu.sh`. Again, look inside the script to make sure that the arguments are appropriate.

# What We've Tried
For evaluation: `bash script/empirical_study/diverse/kpeval_gpu.sh`
This runs a set of pretrained models (take a look at the script to see which) on a dataset (again take a look at the script).

For training: `bash script/empirical_study/diverse/rnn/rnn-presabs-kp20k.sh`
This runs the training regimen from [Yuan et al.](https://arxiv.org/abs/1810.05241)
