#!/usr/bin/env bash
#SBATCH --cluster=gpu
#SBATCH --gres=gpu:1
#SBATCH --account=hdaqing

#SBATCH --partition={partition}

#SBATCH --job-name={job_name}
#SBATCH --output={slurm_output_dir}/{job_name}.out
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16GB
#SBATCH --time={days}-00:00:00 # 6 days walltime in dd-hh:mm format
#SBATCH --qos=long

cmd="python kp_gen_eval_transfer.py -config config/transfer_kp/infer/keyphrase-one2seq.yml -tasks pred -data_dir /home/ubuntu/ -exp_root_dir /home/ubuntu/transformer-presabs-kptimes-bart-trial-01 -testsets kptimes_NYTimes500 -splits test -batch_size 32 -beam_size 1 -max_length 32 -beam_terminate full --step_base 1 --data_format jsonl --pred_trained_only -gpu 0 -onepass"
echo $cmd
echo $PWD
$cmd
