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

#source ~/.bash_profile # reload LD_LIBRARY due to error ImportError: /lib64/libstdc++.so.6: version `GLIBCXX_3.4.21' not found
cmd="python kp_gen_eval_transfer.py -config config/diversity/keyphrase-one2seq-diversity.yml -tasks {task_args} -data_dir ~/data/json/ -exp_root_dir {exp_root_dir} -testsets {dataset_args} -splits test -batch_size {batch_size} -beam_size {beam_size} -max_length {max_length} -beam_terminate full --step_base {step_base} --data_format jsonl --pred_trained_only -gpu 0"

#echo $cmd
#echo $PWD
$cmd
