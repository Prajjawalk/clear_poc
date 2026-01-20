```python
 # Load model and tokenizer
print(f"\nLoading model from: {model_path}")
tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForSequenceClassification.from_pretrained(model_path)
model.eval()  # Set to evaluation mode

# Load test data
print(f"Loading test data from: {test_csv_path}")
test_df = pd.read_csv(test_csv_path)
print(f"Test samples: {len(test_df)}")

# Prepare inputs
headlines = test_df['headline'].tolist()
true_labels = test_df['alert_binary'].tolist()

# Tokenize
inputs = tokenizer(
    headlines,
    truncation=True,
    padding='max_length',
    max_length=64,
    return_tensors='pt'
)

# Predict
print("\nRunning inference on test set...")
with torch.no_grad():
    outputs = model(**inputs)
    logits = outputs.logits
    probs = torch.softmax(logits, dim=-1)
    predictions = logits.argmax(dim=-1).numpy()
    probabilities = probs[:, 1].numpy()  # Probability of class 1 (alert)
```
