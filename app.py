"""Thread & Form: Flask clothing catalogue and persistent review workflow."""
import csv, os, pickle, re, secrets, sqlite3
from pathlib import Path
from collections import Counter
from flask import Flask, render_template, request, abort, redirect, url_for, session
ROOT=Path(__file__).resolve().parent

def tokens(text):
    """Normalize common clothing singular/plural forms; match all query terms."""
    aliases={'dresses':'dress','jeans':'jean','pants':'pant','trousers':'trouser','shorts':'short','skirts':'skirt','tops':'top','blouses':'blouse','sweaters':'sweater','jackets':'jacket','shirts':'shirt','knits':'knit','chemises':'chemise','intimates':'intimate','layers':'layer','blazers':'blazer','lounges':'lounge'}
    return {aliases.get(w,w[:-1] if w.endswith('s') and not w.endswith(('ss','us')) else w) for w in re.findall(r'[a-z0-9]+',text.lower())}

def create_app(database=None):
    app=Flask(__name__)
    secret=ROOT/'data/.session-key'
    if not secret.exists(): secret.write_text(secrets.token_hex(32))
    app.secret_key=os.environ.get('SECRET_KEY',secret.read_text())
    app.config.update(DATABASE=str(database or ROOT/'data/reviews.sqlite3'),MAX_CONTENT_LENGTH=32000,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax')
    def db():
        con=sqlite3.connect(app.config['DATABASE']); con.row_factory=sqlite3.Row; return con
    with db() as con:
        con.execute('CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY, clothing_id INTEGER NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), predicted INTEGER NOT NULL, recommended INTEGER NOT NULL, token TEXT UNIQUE NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    with (ROOT/'data/assignment3_II.csv').open(encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
    catalogue={}; originals={}
    # One product per Clothing ID; the first row supplies canonical generated metadata.
    for r in rows:
        pid=int(r['Clothing ID']); originals.setdefault(pid,[]).append(r)
        if pid not in catalogue:
            p={'id':pid,'title':r['Clothes Title'] or f'Clothing {pid}','description':r['Clothes Description'],'division':r['Division Name'] or 'Other','department':r['Department Name'] or 'Other','category':r['Class Name'] or 'Other'}
            p['terms']=tokens(' '.join(str(v) for v in p.values())); catalogue[pid]=p
    products=list(catalogue.values())
    for p in products:
        ratings=[int(r['Rating']) for r in originals[p['id']] if r['Rating']]; p['average']=round(sum(ratings)/len(ratings),1) if ratings else 0; p['count']=len(ratings)
    with (ROOT/'models/recommender.pkl').open('rb') as f: model=pickle.load(f)
    groups={d:sorted({p['category'] for p in products if p['department']==d}) for d in sorted({p['department'] for p in products})}
    def product(pid):
        if pid not in catalogue: abort(404)
        return catalogue[pid]
    @app.context_processor
    def context():
        session.setdefault('csrf',secrets.token_hex(24))
        return {'groups':groups,'csrf':session['csrf']}
    @app.before_request
    def protect():
        if request.method=='POST' and (not session.get('csrf') or request.form.get('csrf')!=session['csrf']): abort(400)
    @app.get('/')
    def home():
        q=request.args.get('q','').strip()[:200]; department=request.args.get('department',''); category=request.args.get('category','')
        found=[p for p in products if (not department or p['department']==department) and (not category or p['category']==category) and tokens(q)<=p['terms']]
        page=max(1,request.args.get('page',1,type=int)); pages=max(1,(len(found)+11)//12); page=min(page,pages)
        return render_template('home.html',products=found[(page-1)*12:page*12],total=len(found),q=q,department=department,category=category,page=page,pages=pages)
    @app.get('/items/<int:pid>')
    def detail(pid):
        p=product(pid)
        with db() as con: reviews=con.execute('SELECT * FROM reviews WHERE clothing_id=? ORDER BY id DESC',(pid,)).fetchall()
        page=max(1,request.args.get('page',1,type=int)); historic=originals[pid]; pages=max(1,(len(historic)+9)//10); page=min(page,pages)
        return render_template('detail.html',p=p,reviews=reviews,originals=historic[(page-1)*10:page*10],page=page,pages=pages)
    @app.route('/items/<int:pid>/review',methods=['GET','POST'])
    def new_review(pid):
        p=product(pid); error=None
        if request.method=='POST':
            title=request.form.get('title','').strip(); body=request.form.get('body','').strip(); rating=request.form.get('rating','')
            if not 1<=len(title)<=120 or not 10<=len(body)<=5000 or rating not in ('1','2','3','4','5'):
                error='Enter a title (1–120 characters), review (10–5,000 characters), and rating (1–5).'
            else:
                predicted=int(model.predict([body])[0])
                session['draft']={'pid':pid,'title':title,'body':body,'rating':int(rating),'predicted':predicted,'token':secrets.token_hex(24)}
                # Keep review text server-side: Flask cookie would exceed browser limits.
                drafts=ROOT/'data/drafts'; drafts.mkdir(exist_ok=True)
                import json
                draft=session.pop('draft'); (drafts/(draft['token']+'.json')).write_text(json.dumps(draft))
                session['draft_token']=draft['token']
                return redirect(url_for('confirm',pid=pid))
        return render_template('new.html',p=p,error=error)
    @app.route('/items/<int:pid>/confirm',methods=['GET','POST'])
    def confirm(pid):
        import json
        p=product(pid); token=session.get('draft_token','')
        if not re.fullmatch('[0-9a-f]{48}',token): return redirect(url_for('new_review',pid=pid))
        path=ROOT/'data/drafts'/f'{token}.json'
        if not path.exists(): return redirect(url_for('new_review',pid=pid))
        draft=json.loads(path.read_text())
        if draft['pid']!=pid: abort(400)
        if request.method=='POST':
            recommendation=request.form.get('recommended')
            if recommendation not in ('0','1'): abort(400)
            with db() as con:
                con.execute('INSERT OR IGNORE INTO reviews(clothing_id,title,body,rating,predicted,recommended,token) VALUES(?,?,?,?,?,?,?)',(pid,draft['title'],draft['body'],draft['rating'],draft['predicted'],int(recommendation),token))
                rid=con.execute('SELECT id FROM reviews WHERE token=?',(token,)).fetchone()['id']
            path.unlink(missing_ok=True); session.pop('draft_token',None)
            return redirect(url_for('review',rid=rid))
        return render_template('confirm.html',p=p,draft=draft)
    @app.get('/reviews/<int:rid>')
    def review(rid):
        with db() as con: r=con.execute('SELECT * FROM reviews WHERE id=?',(rid,)).fetchone()
        if r is None: abort(404)
        return render_template('review.html',r=r,p=product(r['clothing_id']))
    @app.errorhandler(404)
    @app.errorhandler(400)
    def error(e): return render_template('error.html',message='Page not found.' if e.code==404 else 'Invalid request. Reload the form and try again.'),e.code
    return app
if __name__=='__main__': create_app().run(host='127.0.0.1',port=5000,debug=False)
