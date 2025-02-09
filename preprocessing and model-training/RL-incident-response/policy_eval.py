import itertools
import json
from pathlib import Path
from CybORG.Agents.Wrappers import ChallengeWrapper
from cyborg_wrappers.base_wrapper import cyborg_env, get_scenario_path

from stable_baselines3 import PPO
from tqdm import tqdm
import cyborg_wrappers.graphwrapper as graphwrapper
import time
from CybORG.Simulator.Actions.AbstractActions import Impact
import gymnasium
from CybORG import CybORG as CybORGEnv
import torch
import numpy as np
import random
import sys
import gnn

sys.modules['oracle_sage'] = gnn
sys.modules['oracle_sage.sage.agent'] = gnn

import csv


import re

graphwrapper.register_env()

import csv

import csv

def render_step(attacker_action, defender_action, blue_table, steps, csv_filename='actions_list.csv'):
    # Prepare data for the row
    if hasattr(defender_action, "hostname"):
        hostname = defender_action.hostname
        host_state = blue_table[hostname]
        activity = host_state[3]
        compromised = host_state[4]
    else:
        host_state = "N/A"
        hostname = "N/A"
        activity = "N/A"
        compromised = "N/A"

    data_row = [
        steps,
        str(defender_action),
        activity,
        compromised,
        str(attacker_action)
    ]

    # Open the CSV file, write the row, and close the file
    with open(csv_filename, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(data_row)


@torch.inference_mode()
def run_single_episode(env, model, seed, render=True): #raddineha true
    done = False
    average_inference_time = 0
    steps = 0
    obs, _ = env.reset(seed=seed)
    rewards = []
    operations_hacked = False
    while not done:
        # measure time it takes to predict
        before = time.time()
        action, _ = model.predict(obs)
        after = time.time()
        average_inference_time += after - before

        obs, reward, term, trunc, _ = env.step(action)
        defender_action = env.unwrapped.env.get_last_action("Blue")
        attacker_action = env.unwrapped.env.get_last_action("Red")
        if (
            isinstance(attacker_action, Impact)
            and attacker_action.hostname == "Op_Server0"
        ):
            operations_hacked = True

        if render:
            blue_table = (
                env.unwrapped.env.env.env.info.copy()
                if isinstance(env.unwrapped, CybORGEnv)
                else env.unwrapped.env.env.env.info.copy()
            )
            render_step(attacker_action, defender_action, blue_table, steps)

        steps += 1
        rewards.append(reward)
        if trunc or term:
            done = True

    _return = sum(rewards)
    if render:
        print("Average inference time: ", average_inference_time / steps)
        print("Return: ", _return)
        print("Operations hacked: ", operations_hacked)
    return _return


def evaluate_policy(model, seed, env, n_eval_episodes=2):
    _returns = [
        run_single_episode(env, model, seed, render=True)
        for _ in tqdm(range(n_eval_episodes))
    ]
    return _returns


@torch.inference_mode()
def eval_mlp(model, max_steps, red_agent, scenario_file=None):
    seed = 1

    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)

    env = cyborg_env(scenario_file_path=scenario_file, agent=red_agent)
    env = ChallengeWrapper("Blue", env)
    env = gymnasium.wrappers.EnvCompatibility(env)
    env = gymnasium.wrappers.TimeLimit(env, max_episode_steps=max_steps)

    rewards = evaluate_policy(model, seed, env, n_eval_episodes=100)

    return rewards


@torch.inference_mode()
def evaluate(model_file, eval_func,red_agentt="meander", scenario_file=None):
    print(model_file)
    red_agents = [red_agentt]
    episode_lengths = [1]
    model = PPO.load(model_file)

    def func(red_agent, episode_length):
        tqdm.write(
            f"Evaluating {model_file.stem} against {red_agent} with {episode_length} steps on {scenario_file.stem}"
        )
        rewards = eval_func(
            model, episode_length, red_agent, scenario_file=scenario_file
        )

        return (
            (episode_length, red_agent, model_file.stem, scenario_file.stem, r)
            for r in rewards
        )

    results = (
        r
        for red_agent in red_agents
        for episode_length in episode_lengths
        for r in func(red_agent, episode_length)
    )

    return results


def test_MLP_different_graphs(model_dir,red_agent, scenario_dir):
    scenario_to_model = lambda scenario: model_dir / re.search(
        r"variant\d", scenario.stem
    ).group(0)
    print(scenario_to_model)
    results = (
        evaluate(
            model_file=scenario_to_model(scenario),
            eval_func=eval_mlp,
            red_agentt=red_agent,
            scenario_file=scenario
        )
        for scenario in sorted(scenario_dir.glob("*4.yaml"))
        )

    return results

def save_results(results, filename):
    with open(filename, "w") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["Episode Length", "Red Agent", "Model", "Scenario", "Reward", "Std"]
        )
        for result in tqdm(results):
            for r in result:
                writer.writerow(r)


def different_graphs(red_agent):
    scenario_dir = Path("scenarios")
    model_dir = Path("trained_agents")
    results_mlp = test_MLP_different_graphs(model_dir / "mlps",red_agent, scenario_dir)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor() as executor:
        all_results = itertools.chain(results_mlp)
        results = list(executor.map(list, all_results))

        save_results(results, "shuffledresults.csv")

different_graphs("meander")