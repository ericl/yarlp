"""
Tensorflow framework for models
"""

import tensorflow as tf
import numpy as np


class Graph:
    """
    Tensorflow Graph interface
    """

    def __init__(self):
        self._graph = tf.Graph()
        self._session = tf.Session('', graph=self._graph)

    def __enter__(self):
        self._context = self._graph.as_default()
        self._context.__enter__()
        return self

    def __exit__(self, *args):
        self._session.run(
            tf.variables_initializer(self.GLOBAL_VARIABLES)
        )
        self._graph.finalize()
        self._context.__exit__(*args)

    def __contains__(self, var_name):
        return var_name in self._graph.get_all_collection_keys()

    def __setitem__(self, var_name, tf_node):
        # Collections are not sets, so it's possible to add several times
        if var_name in self:
            raise KeyError('"%s" is already in the graph.' % var_name)
        self._graph.add_to_collection(var_name, tf_node)

    def __getitem__(self, var_names):
        if isinstance(var_names, list):
            return [self[v] for v in var_names]

        if var_names not in self:
            raise KeyError('"%s" does not exist in the graph.' % var_names)
        return self._graph.get_collection(var_names)[0]

    def __call__(self, ops, feed_dict={}):
        return self._session.run(ops, feed_dict)

    @property
    def GLOBAL_VARIABLES(self):
        return self._graph.get_collection(tf.GraphKeys.GLOBAL_VARIABLES)

    @property
    def TRAINABLE_VARIABLES(self):
        return self._graph.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES)


class Model:
    """
    A Tensorflow model
    """

    def __init__(self, env, build_graph, build_update_feed_dict):
        """
        """
        self._env = env
        self.G = Graph()
        self._loss = None
        self._optimizer = None
        self._optimizer_op = None

        with self.G:
            build_graph(self)
            self.create_weight_setter_ops()
            self.build_update_feed_dict = build_update_feed_dict

    def update(self, *args):
        # this is how we update the weights
        assert self._optimizer_op is not None

        feed_dict = self.build_update_feed(*args)
        _, loss = self.G([self._optimizer_op, self._loss], feed_dict)

        return loss

    def build_update_feed(self, *args):
        """Create the feed dict for self.update
        """
        return self.build_update_feed_dict(self, *args)

    @property
    def env(self):
        return self._env

    def get_env_action_space_dimension(self):
        if hasattr(self._env.action_space, 'n'):
            return self._env.action_space.n
        return self._env.action_space.shape[0]

    @property
    def weights(self):
        return self.G.TRAINABLE_VARIABLES

    @weights.setter
    def weights(self, weights):
        feed_dict = {
            self.G['weight_input_var:' + n]: w
            for n, w in weights.items()
        }
        ops = [self.G['set_weight_op:' + n] for n in weights]
        self.G(ops, feed_dict)

    def get_weight_names(self):
        return [w.name for w in self.G.TRAINABLE_VARIABLES]

    def get_weights(self):
        """ get weight values """
        return self.G(self.weights)

    def set_weights(self, weights):
        """Set weights in model from a list of weight values"""
        weight_dict = {w.name: val for w, val in zip(self.weights, weights)}
        self.weights = weight_dict

    @property
    def loss(self):
        return self._loss

    @loss.setter
    def loss(self, loss):
        self._loss = loss

    @property
    def optimizer(self):
        return self._optimizer

    @optimizer.setter
    def optimizer(self, optimizer):
        self._optimizer = optimizer

        assert self._loss is not None
        self._optimizer_op = self._optimizer.minimize(self._loss)

    def add_input(self, name='', dtype=tf.float32, shape=None):
        if shape is None:
            shape = (None, self.env.observation_space.shape[0])

        self.input_node = tf.placeholder(
            dtype=dtype,
            shape=shape)

        self.G['input:' + name] = self.input_node

        return self.input_node

    def add_output(self, network, num_outputs=None, name='', dtype=tf.float32):
        """ Add output node created from network
        """
        if num_outputs is None:
            num_outputs = self.get_env_action_space_dimension()

        output_node = network(
            inputs=self.input_node, num_outputs=num_outputs)

        self.G['output:' + name] = output_node

        return output_node

    def add_output_node(self, node, name=''):
        """ Add output node
        """
        self.G['output:' + name] = node
        return node

    def create_weight_setter_ops(self):
        for w in self.weights:
            w_input = tf.placeholder_with_default(w, w.get_shape())
            self.G['weight_input_var:' + w.name] = w_input
            self.G['set_weight_op:' + w.name] = w.assign(w_input)

    def create_gradient_ops_for_node(self,
                                     node, transform_grad_func=lambda x: x):
        grads_and_vars = self.optimizer.compute_gradients(
            node, self.G.TRAINABLE_VARIABLES)

        self.G['gradients:' + node.name] = [
            (transform_grad_func(g), v)
            for g, v in grads_and_vars]

        self.G['gradients_ops:' + node.name] = self.optimizer.apply_gradients(
            self.G['gradients:' + node.name])

    def get_gradients(self, name, feed_dict):
        return self.G(self.G['gradients:' + name], feed_dict)

    def apply_gradient_ops(self, name, feed_dict):
        return self.G(self.G['gradients_ops:' + name], feed_dict)

    def predict(self, data, output_name='output:', input_name='input:'):
        # get the model output for input placeholders
        if len(data.shape) == 1:
            data = np.expand_dims(data, 0)
        output = self.G[output_name]
        feed_dict = {self.G[input_name]: data}
        return self.G(output, feed_dict).flatten()
