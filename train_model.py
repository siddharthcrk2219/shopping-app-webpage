"""Reproduce Milestone I's Bag-of-Words + MultinomialNB experiment."""
import csv, json, pickle
from collections import Counter
from pathlib import Path
import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score, confusion_matrix
from nlp import tokenize_review
ROOT=Path(__file__).resolve().parent

def train():
    with (ROOT/'milestone1/processed.csv').open(encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
    vocab={}
    for line in (ROOT/'milestone1/vocab.txt').read_text().splitlines():
        word,idx=line.rsplit(':',1); vocab[word]=int(idx)
    tokenizer=tokenize_review
    # Use saved count_vectors.txt as the authoritative feature artifact.
    # processed.csv was edited later and drops 40 additional vocabulary terms.
    vectorizer=CountVectorizer(vocabulary=vocab,tokenizer=tokenizer,token_pattern=None,lowercase=False,dtype=np.float32)
    texts=[r['original_review'] for r in rows]; y=np.array([int(r['recommended']) for r in rows])
    train_idx,test_idx=train_test_split(np.arange(len(y)),test_size=.2,random_state=42,stratify=y)
    model=Pipeline([('counts',vectorizer),('classifier',MultinomialNB())])
    model.fit([texts[i] for i in train_idx],y[train_idx])
    # Verify every serialized count vector from Milestone I too.
    matrix=vectorizer.transform(texts)
    with (ROOT/'milestone1/count_vectors.txt').open() as f:
        count=0
        for i,line in enumerate(f):
            parts=line.strip().split(','); assert parts[0]==f'#{i}'
            expected={int(a):int(b) for pair in parts[1:] if pair for a,b in [pair.split(':')]}
            row=matrix.getrow(i); assert dict(zip(row.indices,row.data))==expected
            count+=1
        assert count==len(rows)
    test_texts=[texts[i] for i in test_idx]; target=y[test_idx]; pred=model.predict(test_texts)
    metrics={'model':'Milestone I Bag-of-Words + MultinomialNB, refitted from supplied artifacts','train_reviews':len(train_idx),'test_reviews':len(test_idx),'vocabulary_size':len(vocab),'accuracy':accuracy_score(target,pred),'precision':precision_score(target,pred),'recall':recall_score(target,pred),'f1':f1_score(target,pred),'roc_auc':roc_auc_score(target,model.predict_proba(test_texts)[:,1]),'confusion_matrix':confusion_matrix(target,pred).tolist(),'seed':42,'count_vector_parity_reviews':count,'note':'Preserves Milestone I corpus-wide vocabulary and split. Vocabulary was derived before splitting, so this is reproduction, not a leakage-free new evaluation.'}
    (ROOT/'models').mkdir(exist_ok=True)
    with (ROOT/'models/recommender.pkl').open('wb') as f: pickle.dump(model,f)
    (ROOT/'models/evaluation.json').write_text(json.dumps(metrics,indent=2))
    print(json.dumps(metrics,indent=2))
if __name__=='__main__': train()
