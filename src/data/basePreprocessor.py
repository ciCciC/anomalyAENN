import numpy as np
import pandas as pd
from src.utils.configuration import parquet_engine, credit_data_path, ecg_data_path
import tensorflow as tf
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from abc import ABC, abstractmethod
from imblearn.under_sampling import RandomUnderSampler


class BasePreprocessor(ABC):

    def __init__(self, file_path: str, name: str):
        self.name = name
        self.dataframe = pd.read_parquet(file_path, engine=parquet_engine)
        self.raw_data = self.dataframe.values
        self.labels = None
        self.data = None

    @abstractmethod
    def _normalize(self):
        pass

    def _train_split_data(self):
        self.train_data, self.test_data, self.train_labels, self.test_labels = train_test_split(
            self.data, self.labels, test_size=0.2, stratify=self.labels, random_state=21
        )

    def _split_normal_and_anomalies(self):
        # transform to boolean
        train_labels = self.train_labels.astype(bool)
        test_labels = self.test_labels.astype(bool)

        # subset normal data
        self.normal_train = self.train_data[train_labels]
        self.normal_test = self.test_data[test_labels]

        # subset anomaly data
        self.anom_train = self.train_data[~train_labels]
        self.anom_test = self.test_data[~test_labels]

    def get_all_data(self):
        return self.train_data, self.test_data, self.normal_train, self.normal_test, self.anom_train, self.anom_test

    def get_normalized_data(self):
        x_stacked = np.vstack((self.train_data.numpy(), self.test_data.numpy()))
        y_stacked = np.vstack((np.expand_dims(self.train_labels, axis=1), np.expand_dims(self.test_labels, axis=1)))
        all_norm_data = np.hstack((x_stacked, y_stacked))

        normal_idx = np.where(all_norm_data[:, -1] == 0)[0]
        anomaly_idx = np.where(all_norm_data[:, -1] == 1)[0]

        under_sampled_idx = None
        normal = None
        anomaly = None

        if len(normal_idx) > len(anomaly_idx):
            under_sampled_idx = np.random.choice(normal_idx, len(anomaly_idx), replace=False)
            normal = all_norm_data[under_sampled_idx]
            anomaly = all_norm_data[anomaly_idx]
        else:
            under_sampled_idx = np.random.choice(anomaly_idx, len(normal_idx), replace=False)
            normal = all_norm_data[normal_idx]
            anomaly = all_norm_data[under_sampled_idx]

        evenly_distributed = np.vstack((normal, anomaly))
        data = evenly_distributed[:, :-1]
        labels = evenly_distributed[:, -1]

        return data, labels


class CreditProcessor(BasePreprocessor):
    """
    Creditcard -> https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud
    """

    def __init__(self):
        super().__init__(credit_data_path, 'Credit Card')

        self.labels = 1 - self.raw_data[:, -1]
        self.data = self.raw_data[:, 1:-1]

        self._under_sample()
        self._train_split_data()
        self._normalize()
        self._split_normal_and_anomalies()

    def _under_sample(self):
        under_sampler = RandomUnderSampler(sampling_strategy=.1)
        self.data, self.labels = under_sampler.fit_resample(self.data, self.labels)

    def _normalize(self):
        train_amounts = self.train_data[:, -1].reshape(-1, 1)
        test_amounts = self.test_data[:, -1].reshape(-1, 1)

        scaler = StandardScaler()
        scaler.fit(train_amounts)

        # normalize data
        self.train_data[:, -1] = scaler.transform(train_amounts).squeeze()
        self.test_data[:, -1] = scaler.transform(test_amounts).squeeze()

        # cast to float32
        self.train_data = tf.cast(self.train_data, tf.float32)
        self.test_data = tf.cast(self.test_data, tf.float32)


class ECGProcessor(BasePreprocessor):
    """
    ECG -> https://storage.googleapis.com/download.tensorflow.org/data/ecg.csv
    """

    def __init__(self):
        super().__init__(ecg_data_path, 'Electrocardiogram')

        self.labels = self.raw_data[:, -1]
        self.data = self.raw_data[:, :-1]

        self._train_split_data()
        self._normalize()
        self._split_normal_and_anomalies()

    def _normalize(self):
        # obtain min and max values for normalization
        min_val = tf.reduce_min(self.train_data)
        max_val = tf.reduce_max(self.train_data)

        # normalize data
        self.train_data = (self.train_data - min_val) / (max_val - min_val)
        self.test_data = (self.test_data - min_val) / (max_val - min_val)

        # cast to float32
        self.train_data = tf.cast(self.train_data, tf.float32)
        self.test_data = tf.cast(self.test_data, tf.float32)


__data_type_map = {
    'ecg_data': ECGProcessor,
    'creditcard_data': CreditProcessor
}


def data_factory(dataset_type: str) -> BasePreprocessor:
    if dataset_type not in __data_type_map:
        raise FileNotFoundError()

    return __data_type_map[dataset_type]()
