import numpy as np

from keras.models import Model
from keras import backend as K
from keras.optimizers import Adam
from keras.callbacks import ModelCheckpoint
import tensorflow as tf

class NetworkManager:
    '''
    Helper class to manage the generation of subnetwork training given a dataset
    '''
    def __init__(self, dataset, epochs=5, batchsize=128, use_generator=False, monitor='val_acc'):
        '''
        Manager which is tasked with creating subnetworks, training them on a dataset, and retrieving
        rewards in the term of accuracy, which is passed to the controller RNN.

        Args:
            dataset: a tuple of 4 arrays (X_train, y_train, X_val, y_val)
            epochs: number of epochs to train the subnetworks
            batchsize: batchsize of training the subnetworks
            acc_beta: exponential weight for the accuracy
            clip_rewards: whether to clip rewards in [-0.05, 0.05] range to prevent
                large weight updates. Use when training is highly unstable.
            use_generator: whether to use a keras generator for training instead of a static dataset
                - in the case of a generator, dataset is expected to be a tuple 
                  (training_generator, validation_generator).
            monitor: monitor argument to pass to the ModelCheckpoint keras callback. E.g. 'val_loss',
                or 'val_acc' for regression or classification, respectively.
        '''
        self.dataset = dataset
        self.epochs = epochs
        self.batchsize = batchsize
        self.use_generator = use_generator
        self.monitor = monitor

    def get_rewards(self, model_fn, actions):
        '''
        Creates a subnetwork given the actions predicted by the controller RNN,
        trains it on the provided dataset, and then returns a reward.

        Args:
            model_fn: a function which accepts one argument, a list of
                parsed actions, obtained via an inverse mapping from the
                StateSpace.
            actions: a list of parsed actions obtained via an inverse mapping
                from the StateSpace. It is in a specific order as given below:

                Consider 4 states were added to the StateSpace via the `add_state`
                method. Then the `actions` array will be of length 4, with the
                values of those states in the order that they were added.

                If number of layers is greater than one, then the `actions` array
                will be of length `4 * number of layers` (in the above scenario).
                The index from [0:4] will be for layer 0, from [4:8] for layer 1,
                etc for the number of layers.

                These action values are for direct use in the construction of models.

        Returns:
            a reward for training a model with the given actions
        '''
        with tf.Session(graph=tf.Graph()) as network_sess:
            K.set_session(network_sess)

            # generate a submodel given predicted actions
            model = model_fn(actions)  # type: Model
            optimizer = Adam(lr=1e-3, amsgrad=True)
            model.compile(optimizer, 'categorical_crossentropy', metrics=['accuracy'])

            if not self.use_generator:
                # unpack the dataset
                X_train, y_train, X_val, y_val = self.dataset
                
                # train the model using Keras methods
                model.fit(X_train, y_train, batch_size=self.batchsize, epochs=self.epochs,
                          verbose=1, validation_data=(X_val, y_val),
                          callbacks=[ModelCheckpoint('weights/temp_network.h5',
                                                     monitor=self.monitor, verbose=1,
                                                     save_best_only=True,
                                                     save_weights_only=True)])
            else:
                training_generator, validation_generator = self.dataset
                model.fit_generator(
                    generator=training_generator,
                    validation_data=validation_generator,
                    use_multiprocessing=True,
                    epochs=self.epochs,
                    verbose=1,
                    workers=6,
                    callbacks=[ModelCheckpoint('weights/temp_network.h5',
                                                     monitor='val_acc', verbose=1,
                                                     save_best_only=True,
                                                     save_weights_only=True)]
                )            
            # load best performance epoch in this training session
            model.load_weights('weights/temp_network.h5')

            # evaluate the model
            loss, acc = model.evaluate(X_val, y_val, batch_size=self.batchsize)

            # compute the reward
            reward = acc

            print()
            print("Manager: Accuracy = ", reward)

        # clean up resources and GPU memory
        network_sess.close()

        return reward
