#!/usr/bin/env bash
#SBATCH --cluster=gpu
#SBATCH --gres=gpu:2
#SBATCH --partition=titanx
#SBATCH --partition=gtx1080s
#SBATCH --partition=v100
#SBATCH --account=hdaqing

#SBATCH --job-name=train-bart-kptimes-rerun
#SBATCH --output=slurm_output/train-bart-kptimes-rerun.out
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=32GB
#SBATCH --time=0-20:00:00 # 6 days walltime in dd-hh:mm format
#SBATCH --qos=long

# Load modules
#module restore
#module load cuda/10.0.130
#module load gcc/6.3.0
#module load python/anaconda3.6-5.2.0
#source activate py36
#module unload python/anaconda3.6-5.2.0

# GPU usage: --max-tokens=1536,--update-freq=16, bsz=110: k+MiB / 32480MiB
#cd /zfs1/hdaqing/rum20/kp/fairseq-kpg/fairseq_cli/
#export WANDB_NAME=bartFT_presabs_kptimes_100kstep
#export TOKENIZERS_PARALLELISM=false
cmd="python train.py -config script/transfer/train_fulldata/kpgen-bart-presabs-kptimes.yml"



echo $CONFIG_PATH
echo $cmd

$cmd
