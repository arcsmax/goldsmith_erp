"""
ML package for Goldsmith ERP.

Provides feature engineering, categorical encoding, and dataset construction
for time-estimation and anomaly-detection models.

Typical usage
-------------
from goldsmith_erp.ml.feature_engineering import FeatureEngineer
from goldsmith_erp.ml.encoders import encode_metal_type, encode_order_type
from goldsmith_erp.ml.constants import TARGET_VARIABLE, NUMERIC_FEATURES

engineer = FeatureEngineer()
feature_vector = await engineer.build_feature_vector(db, order)
training_rows   = await engineer.build_training_dataset(db)
"""
