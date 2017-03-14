import numpy as np
import tensorflow as tf

from yarlp.model.tf_model import Model
from functools import partial


# TODO, the factory should be able to discern whether an env
# is discrete or continuous

def cem_model_factory(env, network=tf.contrib.layers.fully_connected):
    """ Network for CEM agents
    """

    def build_graph(model, network):
        model.add_input()
        from functools import partial
        network = partial(network, activation_fn=tf.nn.softmax)
        model.add_output(network)

    def build_update_feed_dict(model):
        pass

    build_graph = partial(build_graph, network=network)

    return Model(env, build_graph, build_update_feed_dict)


def value_function_model_factory(
        env, network=tf.contrib.layers.fully_connected,
        learning_rate=0.01):
    """ Minimizes squared error of state-value function
    """

    def build_graph(model, network):
        input_node = model.add_input()

        network = partial(network, activation_fn=None)
        output_node = model.add_output(network, num_outputs=1)

        # Value function estimation stuff
        model.state = input_node
        model.target_value = tf.placeholder(
            dtype=tf.float32, shape=(None,), name='target_value')
        model.loss = tf.squared_difference(output_node, model.target_value)
        model.optimizer = tf.train.AdamOptimizer(
            learning_rate=learning_rate)

    def build_update_feed_dict(model, state, target_value):
        feed_dict = {model.state: np.expand_dims(state, 0),
                     model.target_value: [target_value]}
        return feed_dict

    build_graph = partial(build_graph, network=network)

    return Model(env, build_graph, build_update_feed_dict)


def policy_gradient_model_factory(
        env, network=tf.contrib.layers.fully_connected,
        learning_rate=0.01, action_space='discrete'):
    """ Vanilla policy gradient for discrete and continuous action spaces

    type : str
        whether the action space is 'continuous' or 'discrete'
    """

    def build_graph(model, network, action_space):
        input_node = model.add_input()

        model.state = input_node
        model.Return = tf.placeholder(
            dtype=tf.float32, shape=(None,), name='return')

        # Policy gradient stuff
        if action_space == 'discrete':
            # Softmax policy for discrete action spaces
            network = partial(network, activation_fn=tf.nn.softmax)
            output_node = model.add_output(network)

            model.action = tf.placeholder(
                dtype=tf.int32, shape=(None,), name='action')
            action_probability = tf.gather(
                tf.squeeze(output_node), model.action)

            model.loss = -tf.log(action_probability) * model.Return
        elif action_space == 'continuous':
            # Gaussian policy is natural to use in continuous action spaces
            # http://home.deib.polimi.it/restelli/MyWebSite/pdf/rl7.pdf
            network = partial(network, activation_fn=None)
            model.mu = model.add_output(network, name='mean')
            model.sigma = model.add_output(network, name='std_dev')

            model.normal_dist = tf.contrib.distributions.Normal(
                model.mu, model.sigma)
            model.action = tf.squeeze(model.normal_dist.sample([1]))
            model.action = tf.clip_by_value(
                model.action, model._env.action_space.low[0],
                model._env.action_space.high[0])
            model.add_output_node(model.action)

            model.loss = -model.normal_dist.log_prob(
                model.action) * model.Return
            model.loss -= 0.1 * model.normal_dist.entropy()
        else:
            raise ValueError('%s is not a valid action_space' % action_space)

        model.optimizer = tf.train.AdamOptimizer(
            learning_rate=learning_rate)

    def build_update_feed_dict(model, state, return_, action):
        feed_dict = {model.state: np.array(np.expand_dims(state, 0)),
                     model.Return: [return_], model.action: [action]}
        return feed_dict

    build_graph = partial(build_graph, network=network,
                          action_space=action_space)

    return Model(env, build_graph, build_update_feed_dict)
