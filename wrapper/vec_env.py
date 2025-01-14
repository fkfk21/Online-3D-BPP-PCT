import contextlib
import os
from abc import ABC, abstractmethod
import cv2
from torch.onnx.symbolic_opset9 import view

from .tile_images import tile_images

class AlreadySteppingError(Exception):
    """
    Raised when an asynchronous step is running while
    step_async() is called again.
    """

    def __init__(self):
        msg = 'already running an async step'
        Exception.__init__(self, msg)


class NotSteppingError(Exception):
    """
    Raised when an asynchronous step is not running but
    step_wait() is called.
    """

    def __init__(self):
        msg = 'not running an async step'
        Exception.__init__(self, msg)


class SimpleImageViewer(object):
    def __init__(self):
        self.window_name = "SimpleImageViewer"
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        self.isopen = True

    def imshow(self, arr):
        if self.isopen:
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)  # If the input array is in RGB format, convert it to BGR for OpenCV
            cv2.imshow(self.window_name, arr)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.isopen = False
                self.close()

    def close(self):
        self.isopen = False
        cv2.destroyWindow(self.window_name)

    def __del__(self):
        self.close()

import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import threading

class SimpleViewer(threading.Thread):
    def __init__(self):
        super().__init__()

        # 2D Viewer Initialization
        self.window_name = "SimpleImageViewer"
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        self.isopen_2d = True

        # 3D Viewer Initialization
        self.fig = plt.figure()
        self.ax = self.fig.add_subplot(111, projection='3d')
        self.ax.set_xlabel('X')
        self.ax.set_ylabel('Y')
        self.ax.set_zlabel('Z')
        self.isopen_3d = True

        # self.start()

    def imshow(self, arr):
        if self.isopen_2d:
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)  # If the input array is in RGB format, convert it to BGR for OpenCV
            cv2.imshow(self.window_name, arr)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.isopen_2d = False
                self.close_2d()

    def close_2d(self):
        self.isopen_2d = False
        cv2.destroyWindow(self.window_name)

    # def add_box(self, x, y, z, dx, dy, dz, color='blue'):
    #     """ Adds a box to the scene.

    #     Parameters:
    #     x, y, z: Coordinates of the bottom left corner of the box.
    #     dx, dy, dz: Dimensions of the box along the x, y, and z axes.
    #     color: Color of the box.
    #     """
    #     if self.isopen_3d:
    #         self.ax.bar3d(x, y, z, dx, dy, dz, shade=True, color=color)

    def add_box(self, x, y, z, dx, dy, dz, color='blue'):
        # Define the 8 vertices of the box
        verts = [
            [x, y, z],
            [x+dx, y, z],
            [x+dx, y+dy, z],
            [x, y+dy, z],
            [x, y, z+dz],
            [x+dx, y, z+dz],
            [x+dx, y+dy, z+dz],
            [x, y+dy, z+dz]
        ]

        # Define the 12 triangles composing the box
        faces = [
            [verts[0], verts[1], verts[5], verts[4]],
            [verts[7], verts[6], verts[2], verts[3]],
            [verts[0], verts[4], verts[7], verts[3]],
            [verts[1], verts[5], verts[6], verts[2]],
            [verts[4], verts[5], verts[6], verts[7]],
            [verts[0], verts[1], verts[2], verts[3]]
        ]

        # Create a Poly3DCollection
        box = Poly3DCollection(faces, facecolors='blue', linewidths=1, edgecolors='black', alpha=.5)

        # Add the box to the axes
        self.ax.add_collection3d(box)

    
    def add_boxes(self, packed_boxes):
        if self.isopen_3d:
            self.ax.cla()
            for box in packed_boxes:
                self.add_box(box[3], box[4], box[5], box[0], box[1], box[2])

    def render_3d(self):
        if self.isopen_3d:
            # xyz軸の範囲を0から10まで固定します
            self.ax.set_xlim([0, 10])
            self.ax.set_ylim([0, 10])
            self.ax.set_zlim([0, 10])
            plt.draw()
            plt.pause(0.001)
    
    def run(self):
        self.render_3d()

    def close_3d(self):
        self.isopen_3d = False
        plt.close()

    def close(self):
        self.close_2d()
        self.close_3d()

    def __del__(self):
        self.close()


class VecEnv(ABC):
    """
    An abstract asynchronous, vectorized environment.
    Used to batch data from multiple copies of an environment, so that
    each observation becomes an batch of observations, and expected action is a batch of actions to
    be applied per-environment.
    """
    closed = False
    viewer = None

    metadata = {
        'render.modes': ['human', 'rgb_array']
    }

    def __init__(self, num_envs, observation_space, action_space):
        self.num_envs = num_envs
        self.observation_space = observation_space
        self.action_space = action_space

    @abstractmethod
    def reset(self):
        """
        Reset all the environments and return an array of
        observations, or a dict of observation arrays.

        If step_async is still doing work, that work will
        be cancelled and step_wait() should not be called
        until step_async() is invoked again.
        """
        pass

    @abstractmethod
    def step_async(self, actions):
        """
        Tell all the environments to start taking a step
        with the given actions.
        Call step_wait() to get the results of the step.

        You should not call this if a step_async run is
        already pending.
        """
        pass

    @abstractmethod
    def step_wait(self):
        """
        Wait for the step taken with step_async().

        Returns (obs, rews, dones, infos):
         - obs: an array of observations, or a dict of
                arrays of observations.
         - rews: an array of rewards
         - dones: an array of "episode done" booleans
         - infos: a sequence of info objects
        """
        pass

    def close_extras(self):
        """
        Clean up the  extra resources, beyond what's in this base class.
        Only runs when not self.closed.
        """
        pass

    def close(self):
        if self.closed:
            return
        if self.viewer is not None:
            self.viewer.close()
        self.close_extras()
        self.closed = True

    def step(self, actions):
        """
        Step the environments synchronously.

        This is available for backwards compatibility.
        """
        self.step_async(actions)
        return self.step_wait()

    def render(self, mode='human'):
        # imgs = self.get_images()
        imgs, packed_boxes, leaf_nodes, next_boxes = list(zip(*self.get_images()))
        bigimg = tile_images(imgs)
        if mode == 'human':
            self.get_viewer().imshow(bigimg)
            self.get_viewer().add_boxes(packed_boxes[0])
            self.get_viewer().render_3d()
            return self.get_viewer().isopen_2d and self.get_viewer().isopen_3d
        elif mode == 'rgb_array':
            return bigimg
        else:
            raise NotImplementedError

    def get_images(self):
        """
        Return RGB images from each environment
        """
        raise NotImplementedError

    @property
    def unwrapped(self):
        if isinstance(self, VecEnvWrapper):
            return self.venv.unwrapped
        else:
            return self

    def get_viewer(self):
        if self.viewer is None:
            # from gym.envs.classic_control import rendering
            self.viewer = SimpleViewer()
        return self.viewer

class VecEnvWrapper(VecEnv):
    """
    An environment wrapper that applies to an entire batch
    of environments at once.
    """

    def __init__(self, venv, observation_space=None, action_space=None):
        self.venv = venv
        super().__init__(num_envs=venv.num_envs,
                        observation_space=observation_space or venv.observation_space,
                        action_space=action_space or venv.action_space)

    def step_async(self, actions):
        self.venv.step_async(actions)

    @abstractmethod
    def reset(self):
        pass

    @abstractmethod
    def step_wait(self):
        pass

    def close(self):
        return self.venv.close()

    def render(self, mode='human'):
        return self.venv.render(mode=mode)

    def get_images(self):
        return self.venv.get_images()

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError("attempted to get missing private attribute '{}'".format(name))
        return getattr(self.venv, name)

class VecEnvObservationWrapper(VecEnvWrapper):
    @abstractmethod
    def process(self, obs):
        pass

    def reset(self):
        obs = self.venv.reset()
        return self.process(obs)

    def step_wait(self):
        obs, rews, dones, infos = self.venv.step_wait()
        return self.process(obs), rews, dones, infos

class CloudpickleWrapper(object):
    """
    Uses cloudpickle to serialize contents (otherwise multiprocessing tries to use pickle)
    """

    def __init__(self, x):
        self.x = x

    def __getstate__(self):
        import cloudpickle
        return cloudpickle.dumps(self.x)

    def __setstate__(self, ob):
        import pickle
        self.x = pickle.loads(ob)


@contextlib.contextmanager
def clear_mpi_env_vars():
    """
    from mpi4py import MPI will call MPI_Init by default.  If the child process has MPI environment variables, MPI will think that the child process is an MPI process just like the parent and do bad things such as hang.
    This context manager is a hacky way to clear those environment variables temporarily such as when we are starting multiprocessing
    Processes.
    """
    removed_environment = {}
    for k, v in list(os.environ.items()):
        for prefix in ['OMPI_', 'PMI_']:
            if k.startswith(prefix):
                removed_environment[k] = v
                del os.environ[k]
    try:
        yield
    finally:
        os.environ.update(removed_environment)
