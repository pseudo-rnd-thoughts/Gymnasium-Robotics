import pickle
import warnings

import gymnasium as gym
import numpy as np
import pytest
from gymnasium.envs.mujoco.utils import check_mujoco_reset_state
from gymnasium.envs.registration import EnvSpec
from gymnasium.error import Error
from gymnasium.utils.env_checker import check_env, data_equivalence

import gymnasium_robotics
from tests.utils import all_testing_env_specs, assert_equals

gym.register_envs(gymnasium_robotics)

CHECK_ENV_IGNORE_WARNINGS = [
    f"\x1b[33mWARN: {message}\x1b[0m"
    for message in [
        "This version of the mujoco environments depends on the mujoco-py bindings, which are no longer maintained and may stop working. Please upgrade to the v4 versions of the environments (which depend on the mujoco python bindings instead), unless you are trying to precisely replicate previous works.",
        "This version of the mujoco environments depends on the mujoco-py bindings, which are no longer maintained and may stop working. Please upgrade to the v5 or v4 versions of the environments (which depend on the mujoco python bindings instead), unless you are trying to precisely replicate previous works.",
        "A Box observation space minimum value is -infinity. This is probably too low.",
        "A Box observation space maximum value is infinity. This is probably too high.",
        "For Box action spaces, we recommend using a symmetric and normalized space (range=[-1, 1] or [0, 1]). See https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html for more information.",
    ]
]

# Exclude mujoco_py environments in test_render_modes test due to OpenGL error.
non_mujoco_py_env_specs = [
    spec
    for spec in all_testing_env_specs
    if "MujocoPy" not in spec.entry_point
    and not spec.entry_point.startswith(
        "gymnasium_robotics.envs.mujoco."
    )  # Exclude version 2 and version 3 of the "mujoco" environments
]


@pytest.mark.parametrize(
    "spec", non_mujoco_py_env_specs, ids=[spec.id for spec in non_mujoco_py_env_specs]
)
def test_env(spec):
    # Capture warnings
    env = spec.make(disable_env_checker=True).unwrapped

    warnings.simplefilter("always")
    # Test if env adheres to Gym API
    with warnings.catch_warnings(record=True) as w:
        check_env(env, skip_render_check=True)
        env.close()
    for warning in w:
        if warning.message.args[0] not in CHECK_ENV_IGNORE_WARNINGS:
            raise Error(f"Unexpected warning: {warning.message}")


# Note that this precludes running this test in multiple threads.
# However, we probably already can't do multithreading due to some environments.
SEED = 0
NUM_STEPS = 50


@pytest.mark.parametrize(
    "env_spec", non_mujoco_py_env_specs, ids=[env.id for env in non_mujoco_py_env_specs]
)
def test_env_determinism_rollout(env_spec: EnvSpec):
    """Run a rollout with two environments and assert equality.

    This test run a rollout of NUM_STEPS steps with two environments
    initialized with the same seed and assert that:

    - observation after first reset are the same
    - same actions are sampled by the two envs
    - observations are contained in the observation space
    - obs, rew, terminated, truncated and info are equals between the two envs
    """
    # Don't check rollout equality if it's a nondeterministic environment.
    if env_spec.nondeterministic is True:
        return

    env_1 = env_spec.make(disable_env_checker=True)
    env_2 = env_spec.make(disable_env_checker=True)

    initial_obs_1 = env_1.reset(seed=SEED)
    initial_obs_2 = env_2.reset(seed=SEED)
    assert_equals(initial_obs_1, initial_obs_2)

    env_1.action_space.seed(SEED)

    for time_step in range(NUM_STEPS):
        # We don't evaluate the determinism of actions
        action = env_1.action_space.sample()

        obs_1, rew_1, terminated_1, truncated_1, info_1 = env_1.step(action)
        obs_2, rew_2, terminated_2, truncated_2, info_2 = env_2.step(action)

        assert_equals(obs_1, obs_2, f"[{time_step}] ")
        assert env_1.observation_space.contains(
            obs_1
        )  # obs_2 verified by previous assertion

        assert rew_1 == rew_2, f"[{time_step}] reward 1={rew_1}, reward 2={rew_2}"
        assert (
            terminated_1 == terminated_2
        ), f"[{time_step}] terminated 1={terminated_1}, terminated 2={terminated_2}"
        assert (
            truncated_1 == truncated_2
        ), f"[{time_step}] truncated 1={truncated_1}, truncated 2={truncated_2}"
        assert_equals(info_1, info_2, f"[{time_step}] ")

        if (
            terminated_1 or truncated_1
        ):  # terminated_2 and truncated_2 verified by previous assertion
            env_1.reset(seed=SEED)
            env_2.reset(seed=SEED)

    env_1.close()
    env_2.close()


@pytest.mark.parametrize(
    "env_spec", non_mujoco_py_env_specs, ids=[env.id for env in non_mujoco_py_env_specs]
)
def test_mujoco_reset_state_seeding(env_spec: EnvSpec):
    """Check if the reset method of mujoco environments is deterministic for the same seed.

    Note:
        We exclude mujoco_py environments because they are deprecated and their implementation is
        frozen at this point. They are affected by a subtle bug in their reset method producing
        slightly different results for the same seed on subsequent resets of the same environment.
        This will not be fixed and tests are expected to fail.
    """
    # Don't check rollout equality if it's a nondeterministic environment.
    if env_spec.nondeterministic is True:
        return

    env = env_spec.make(disable_env_checker=True)

    check_mujoco_reset_state(env)


@pytest.mark.parametrize(
    "spec", non_mujoco_py_env_specs, ids=[spec.id for spec in non_mujoco_py_env_specs]
)
def test_render_modes(spec):
    env = spec.make()

    for mode in env.metadata.get("render_modes", []):
        if mode != "human":
            new_env = spec.make(render_mode=mode)

            new_env.reset()
            new_env.step(new_env.action_space.sample())
            new_env.render()

            new_env.close


@pytest.mark.parametrize(
    "env_spec",
    non_mujoco_py_env_specs,
    ids=[spec.id for spec in non_mujoco_py_env_specs],
)
def test_pickle_env(env_spec):
    env: gym.Env = env_spec.make()
    pickled_env: gym.Env = pickle.loads(pickle.dumps(env))

    data_equivalence(env.reset(), pickled_env.reset())

    action = env.action_space.sample()
    data_equivalence(env.step(action), pickled_env.step(action))
    env.close()
    pickled_env.close()


_test_robot_env_reset_list = ["Fetch", "HandReach"]


@pytest.mark.parametrize(
    "spec",
    [
        spec
        for spec in non_mujoco_py_env_specs
        if np.any([tar in spec.id for tar in _test_robot_env_reset_list])
    ],
    ids=[
        spec.id
        for spec in non_mujoco_py_env_specs
        if np.any([tar in spec.id for tar in _test_robot_env_reset_list])
    ],
)
def test_robot_env_reset(spec):
    """Check initial state of robotic environment, i.e. Fetch and Shadow Dexterous Hand Reach,
    whether their initial states match the description in the documentation."""

    def _test_initial_states(env, seed=None):
        diag_dict = {}

        env.reset(seed=seed)

        diag_dict.update(
            {
                "qpos": env.unwrapped.data.qpos,
                "qvel": env.unwrapped.data.qvel,
                "init_qpos": env.unwrapped.initial_qpos,
                "init_qvel": env.unwrapped.initial_qvel,
            }
        )

        # exclude object location from environments
        if np.any(
            [
                tar in spec.id
                for tar in [
                    "FetchPush",
                    "FetchPickAndPlace",
                    "FetchSlide",
                ]
            ]
        ):
            diag_dict["qpos"] = np.delete(diag_dict["qpos"], np.s_[-7:-5])
            diag_dict["init_qpos"] = np.delete(diag_dict["init_qpos"], np.s_[-7:-5])

        # testing
        assert np.all(diag_dict["qpos"] == diag_dict["init_qpos"])
        assert np.all(diag_dict["qvel"] == diag_dict["init_qvel"])
        return diag_dict

    cur_env: gym.Env = spec.make()

    _test_initial_states(cur_env, seed=24)
    _test_initial_states(cur_env, seed=10)
