#!/usr/bin/env bash

# Run the job
export CONFIG_PATH="script/empirical_study/diverse/transformer/transformer-presabs-kptimes.yml"
cmd="python train.py -config $CONFIG_PATH"

echo $CONFIG_PATH
echo $cmd

$cmd
