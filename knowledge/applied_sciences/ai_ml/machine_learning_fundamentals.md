# Machine Learning Fundamentals

## Definition
Machine learning is the field of study that enables systems to learn from data and improve at tasks without being explicitly programmed. An ML model learns a mapping f: X → Y from labeled or unlabeled examples, then generalizes to unseen inputs. Core branches: supervised learning, unsupervised learning, reinforcement learning.

## Core Concepts

### Learning Paradigms
- **Supervised Learning:** Model trained on (input, label) pairs. Goal: learn f(x) ≈ y. Tasks: classification (discrete y) and regression (continuous y). Examples: spam detection, price prediction, image classification.
- **Unsupervised Learning:** No labels. Find structure in data. Clustering (k-means, DBSCAN, hierarchical), dimensionality reduction (PCA, t-SNE, UMAP), generative models (VAE, GAN).
- **Reinforcement Learning (RL):** Agent learns by interacting with an environment, maximizing cumulative reward. Policy π(a|s) maps states to actions. Algorithms: Q-learning, PPO, A3C.
- **Semi-supervised / Self-supervised:** Leverage unlabeled data with small labeled sets. Foundation of modern LLMs (next-token prediction, contrastive learning).

### Model Families
- **Linear Models:** Linear regression (continuous), logistic regression (binary classification). Interpretable, fast, limited to linear decision boundaries. Regularization: L1 (Lasso, sparsity), L2 (Ridge, weight decay).
- **Decision Trees / Ensembles:** Tree splits on features to partition data. Random Forest: bagging of trees (low variance). Gradient Boosted Trees (XGBoost, LightGBM): additive boosting (low bias). Best for tabular data.
- **Support Vector Machines (SVM):** Finds maximum-margin hyperplane. Kernel trick maps to high-dimensional space (RBF, polynomial kernels). Effective in high-dimensional, small-sample problems.
- **Neural Networks:** Layers of parameterized nonlinear transformations. f(x) = activation(Wx + b). Deep learning = many layers. Architecture variants: MLP, CNN (images), RNN/LSTM (sequences), Transformer (attention-based, dominant in NLP/vision).
- **k-Nearest Neighbors (kNN):** Non-parametric. Classify by majority vote of k nearest training points. No training phase; slow at inference.

### Training Process
```
Loss L(y_pred, y_true) → gradient ∇L → update weights W ← W - η∇L
```
- **Loss functions:** MSE (regression), Cross-entropy (classification), Huber (robust regression).
- **Gradient Descent variants:** SGD, Mini-batch SGD, Adam (adaptive learning rates per parameter), AdamW (Adam + weight decay).
- **Backpropagation:** Chain rule applied to compute gradients through the computational graph.
- **Learning rate:** Critical hyperparameter. Too high = divergence; too low = slow convergence. Schedulers: cosine annealing, warm-up + decay.

### Bias-Variance Tradeoff
```
Expected Error = Bias² + Variance + Irreducible Noise
```
- **High bias (underfitting):** Model too simple. Fix: more capacity, more features.
- **High variance (overfitting):** Model memorizes training data. Fix: regularization, dropout, more data, early stopping.
- **Validation curves:** Plot training vs. validation loss by model complexity.

### Evaluation Metrics
- **Classification:** Accuracy, Precision, Recall, F1-score, AUC-ROC, AUC-PR (imbalanced classes).
- **Regression:** MAE, MSE, RMSE, R² (coefficient of determination).
- **Ranking:** NDCG, MAP.
- **Key principle:** Never evaluate on training data. Use train/validation/test splits or k-fold cross-validation.

### Feature Engineering
- Normalization/standardization: scale features to [0,1] or zero-mean/unit-variance.
- Encoding categoricals: one-hot, label encoding, target encoding, embeddings.
- Feature selection: correlation analysis, mutual information, SHAP values, L1 regularization.
- Imputation: mean/median/mode, k-NN imputation, model-based imputation.

### Model Selection and Tuning
- Hyperparameter search: grid search, random search, Bayesian optimization (Optuna).
- Cross-validation: k-fold, stratified k-fold (for imbalanced), time-series split (for temporal data).
- Baseline first: always establish a simple baseline (e.g., predict mean, most frequent class) before complex models.

## Practical Application
- **Tabular data:** Try XGBoost/LightGBM first. Neural nets rarely outperform on tabular data with small-medium datasets.
- **Images:** CNN (ResNet, EfficientNet) or Vision Transformer. Transfer learning from ImageNet almost always beats training from scratch.
- **Text:** Transformer-based models (BERT, RoBERTa for classification; GPT for generation). Fine-tune pre-trained model rather than training from scratch.
- **Class imbalance:** SMOTE oversampling, class weights in loss function, precision-recall AUC instead of accuracy.
