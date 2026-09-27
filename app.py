from flask import Flask, request, redirect, url_for, session, render_template_string, flash
import sqlite3, hashlib, os
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB = BASE / "church_youth_bible_study.db"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "church-youth-change-this-secret")

CSS = """
*{box-sizing:border-box}body{margin:0;background:#f4f6fb;color:#182033;font-family:Arial,sans-serif}
.wrap{max-width:720px;margin:auto;padding-bottom:90px}.hero{background:linear-gradient(135deg,#315efb,#6947e8);color:white;padding:25px 18px;border-radius:0 0 25px 25px}
main{padding:16px}.card{background:white;border:1px solid #e4e8f0;border-radius:18px;padding:16px;margin:12px 0;box-shadow:0 5px 18px #0000000b}
input,textarea,button{width:100%;padding:13px;margin:6px 0;border:1px solid #dce2ec;border-radius:12px;font-size:15px}
button{background:#315efb;color:white;border:0;font-weight:bold}.badge{display:inline-block;background:#edf1ff;color:#315efb;padding:5px 9px;border-radius:20px;font-size:12px}
nav{position:fixed;bottom:0;left:0;right:0;background:white;border-top:1px solid #ddd;display:flex;justify-content:space-around;padding:10px;z-index:5}
nav a{text-decoration:none;color:#596579;font-size:12px;text-align:center}.muted{color:#718096;font-size:13px}.login{max-width:420px;margin:12vh auto;padding:18px}
a{color:#315efb;text-decoration:none}.row{display:flex;gap:8px;align-items:center}.row>*{flex:1}
"""

T = r"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Church Youth Bible Study</title><style>{{css}}</style></head><body><div class="wrap">{{body|safe}}</div>
{% if user %}<nav><a href="/">🏠<br>Home</a><a href="/announcements">📢<br>News</a><a href="/lessons">📖<br>Lessons</a><a href="/saved">🔖<br>Saved</a><a href="/profile">👤<br>Profile</a></nav>{% endif %}
</body></html>"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS roles(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS users(
 id INTEGER PRIMARY KEY AUTOINCREMENT, role_id INTEGER NOT NULL, username TEXT UNIQUE NOT NULL,
 full_name TEXT NOT NULL, password_hash TEXT NOT NULL, preferred_language TEXT DEFAULT 'en',
 status TEXT DEFAULT 'active', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(role_id) REFERENCES roles(id));
CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY AUTOINCREMENT,name_en TEXT NOT NULL,name_am TEXT);
CREATE TABLE IF NOT EXISTS announcements(
 id INTEGER PRIMARY KEY AUTOINCREMENT,author_id INTEGER NOT NULL,title TEXT NOT NULL,message TEXT NOT NULL,
 is_pinned INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(author_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS lessons(
 id INTEGER PRIMARY KEY AUTOINCREMENT,author_id INTEGER NOT NULL,category_id INTEGER,title TEXT NOT NULL,
 title_am TEXT,content TEXT,bible_reference TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(author_id) REFERENCES users(id),FOREIGN KEY(category_id) REFERENCES categories(id));
CREATE TABLE IF NOT EXISTS audio(id INTEGER PRIMARY KEY AUTOINCREMENT,lesson_id INTEGER,title TEXT,file_path TEXT,
 FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS videos(id INTEGER PRIMARY KEY AUTOINCREMENT,lesson_id INTEGER,title TEXT,video_url TEXT,file_path TEXT,
 FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS social_links(id INTEGER PRIMARY KEY AUTOINCREMENT,lesson_id INTEGER,platform TEXT,title TEXT,url TEXT,
 FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY AUTOINCREMENT,lesson_id INTEGER,user_id INTEGER,comment TEXT,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
 FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS saved_lessons(user_id INTEGER,lesson_id INTEGER,saved_at TEXT DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(user_id,lesson_id),FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
 FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE);
"""

def make_hash(password):
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000).hex()
    return f"pbkdf2_sha256$120000${salt}${digest}"

def verify(stored, password):
    try:
        scheme, it, salt, digest = stored.split("$",3)
        test=hashlib.pbkdf2_hmac("sha256",password.encode(),salt.encode(),int(it)).hex()
        return scheme=="pbkdf2_sha256" and test==digest
    except Exception:
        return False

def conn():
    c=sqlite3.connect(DB)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init_db():
    c=conn()
    c.executescript(SCHEMA)
    c.execute("INSERT OR IGNORE INTO roles(id,name) VALUES (1,'Admin'),(2,'Member')")
    c.execute("INSERT OR IGNORE INTO categories(id,name_en,name_am) VALUES (1,'Bible Study','የመጽሐፍ ቅዱስ ጥናት'),(2,'Teaching','ትምህርት')")
    admin_hash=make_hash("Admin@123")
    c.execute("""INSERT OR IGNORE INTO users(role_id,username,full_name,password_hash,preferred_language)
                 VALUES(1,'admin','Church Admin',?,'am')""",(admin_hash,))
    for i in range(1,30):
        c.execute("""INSERT OR IGNORE INTO users(role_id,username,full_name,password_hash,preferred_language)
                     VALUES(2,?,?,?,'am')""",(f"youth{i:02d}",f"Youth {i}",make_hash("Youth@123")))
    admin_id=c.execute("SELECT id FROM users WHERE username='admin'").fetchone()["id"]
    if c.execute("SELECT COUNT(*) FROM announcements").fetchone()[0]==0:
        c.execute("""INSERT INTO announcements(author_id,title,message,is_pinned)
                     VALUES(?,?,?,1)""",(admin_id,"Welcome | እንኳን ደህና መጣችሁ",
                     "Welcome to the Church Youth Bible Study system. | ወደ የወጣቶች የመጽሐፍ ቅዱስ ጥናት ስርዓት እንኳን በደህና መጣችሁ።"))
    if c.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]==0:
        c.execute("""INSERT INTO lessons(author_id,category_id,title,title_am,content,bible_reference)
                     VALUES(1,1,?,?,?,?,?)""",
                  ("Faith and Hope","እምነት እና ተስፋ",
                   "Starter lesson. This section will contain your prepared Bible-study lessons, teaching notes, audio and video links.",
                   "ሮሜ 10፥17"))
    c.commit(); c.close()

def current_user():
    uid=session.get("uid")
    if not uid:return None
    c=conn()
    u=c.execute("""SELECT u.*,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id
                   WHERE u.id=? AND u.status='active'""",(uid,)).fetchone()
    c.close(); return u

def page(body):
    return render_template_string(T,css=CSS,body=body,user=current_user())

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        c=conn(); u=c.execute("""SELECT u.*,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id
                                  WHERE u.username=? AND u.status='active'""",
                               (request.form.get("username","").strip(),)).fetchone(); c.close()
        if u and verify(u["password_hash"],request.form.get("password","")):
            session["uid"]=u["id"]; return redirect("/")
        flash("Invalid username or password.")
    body="""<div class="login"><div class="card" style="text-align:center"><div style="font-size:55px">📖</div>
    <h1>Church Youth</h1><p class="muted">Bible Study | የመጽሐፍ ቅዱስ ጥናት</p>
    {% for m in get_flashed_messages() %}<p style="color:#c0392b">{{m}}</p>{% endfor %}
    <form method="post"><input name="username" placeholder="Username / የተጠቃሚ ስም" required>
    <input name="password" type="password" placeholder="Password / የይለፍ ቃል" required><button>Sign in | ግባ</button></form>
    <p class="muted">Admin: admin / Admin@123<br>Youth: youth01–youth29 / Youth@123</p></div></div>"""
    return page(body)

@app.route("/logout")
def logout():
    session.clear(); return redirect("/login")

@app.route("/")
def home():
    if not current_user(): return redirect("/login")
    c=conn()
    anns=c.execute("""SELECT a.*,u.full_name author FROM announcements a JOIN users u ON u.id=a.author_id
                      ORDER BY a.is_pinned DESC,a.created_at DESC LIMIT 5""").fetchall()
    lessons=c.execute("""SELECT l.*,u.full_name author,c.name_en category FROM lessons l JOIN users u ON u.id=l.author_id
                         LEFT JOIN categories c ON c.id=l.category_id ORDER BY l.created_at DESC LIMIT 8""").fetchall()
    stats=(c.execute("SELECT COUNT(*) FROM users WHERE status='active'").fetchone()[0],
           c.execute("SELECT COUNT(*) FROM lessons").fetchone()[0],
           c.execute("SELECT COUNT(*) FROM announcements").fetchone()[0])
    c.close()
    u=current_user()
    body=f"""<div class="hero"><h1>Welcome, {u["full_name"]} 👋</h1><p>Church Youth Bible Study | የወጣቶች ጥናት</p></div><main>
    <div class="row"><div class="card" style="text-align:center"><b>{stats[0]}</b><br><span class="muted">Members</span></div>
    <div class="card" style="text-align:center"><b>{stats[1]}</b><br><span class="muted">Lessons</span></div>
    <div class="card" style="text-align:center"><b>{stats[2]}</b><br><span class="muted">News</span></div></div>
    <h2>📢 Announcements | ማስታወቂያ</h2>"""
    for a in anns:
        body+=f"""<div class="card"><span class="badge">{"Pinned" if a["is_pinned"] else "News"}</span>
        <h3>{a["title"]}</h3><p>{a["message"]}</p><span class="muted">{a["author"]}</span></div>"""
    body+="<h2>📖 Recent Lessons | የቅርብ ጊዜ ትምህርቶች</h2>"
    for l in lessons:
        body+=f"""<a href="/lesson/{l["id"]}"><div class="card"><span class="badge">{l["category"] or "Lesson"}</span>
        <h3>{l["title"]} {("— "+l["title_am"]) if l["title_am"] else ""}</h3><p>{l["bible_reference"] or ""}</p>
        <span class="muted">By {l["author"]}</span></div></a>"""
    body+="</main>"; return page(body)

@app.route("/announcements")
def announcements():
    if not current_user(): return redirect("/login")
    c=conn(); rows=c.execute("""SELECT a.*,u.full_name author FROM announcements a JOIN users u ON u.id=a.author_id
                                ORDER BY a.is_pinned DESC,a.created_at DESC""").fetchall(); c.close()
    body='<div class="hero"><h1>📢 Announcements</h1><p>ማስታወቂያዎች</p></div><main>'
    for a in rows: body+=f'<div class="card"><span class="badge">{"Pinned" if a["is_pinned"] else "Announcement"}</span><h3>{a["title"]}</h3><p>{a["message"]}</p><span class="muted">{a["author"]}</span></div>'
    body+="</main>"; return page(body)

@app.route("/lessons")
def lessons():
    if not current_user(): return redirect("/login")
    q=request.args.get("q","").strip(); c=conn()
    if q:
        rows=c.execute("""SELECT l.*,u.full_name author,c.name_en category FROM lessons l JOIN users u ON u.id=l.author_id
                          LEFT JOIN categories c ON c.id=l.category_id WHERE l.title LIKE ? OR l.title_am LIKE ? OR l.content LIKE ?
                          ORDER BY l.created_at DESC""",(f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
    else:
        rows=c.execute("""SELECT l.*,u.full_name author,c.name_en category FROM lessons l JOIN users u ON u.id=l.author_id
                          LEFT JOIN categories c ON c.id=l.category_id ORDER BY l.created_at DESC""").fetchall()
    c.close()
    body=f'<div class="hero"><h1>📖 Lessons</h1><p>ትምህርቶች</p></div><main><form><input name="q" value="{q}" placeholder="Search | ፈልግ..."><button>Search | ፈልግ</button></form>'
    for l in rows: body+=f'<a href="/lesson/{l["id"]}"><div class="card"><span class="badge">{l["category"] or "Lesson"}</span><h3>{l["title"]}</h3><p>{l["title_am"] or ""}<br>{l["bible_reference"] or ""}</p><span class="muted">By {l["author"]}</span></div></a>'
    body+="</main>"; return page(body)

@app.route("/lesson/<int:lid>")
def lesson(lid):
    if not current_user(): return redirect("/login")
    c=conn(); l=c.execute("""SELECT l.*,u.full_name author,c.name_en category FROM lessons l JOIN users u ON u.id=l.author_id
                             LEFT JOIN categories c ON c.id=l.category_id WHERE l.id=?""",(lid,)).fetchone()
    if not l: c.close(); return "Lesson not found",404
    audio=c.execute("SELECT * FROM audio WHERE lesson_id=?",(lid,)).fetchall()
    videos=c.execute("SELECT * FROM videos WHERE lesson_id=?",(lid,)).fetchall()
    links=c.execute("SELECT * FROM social_links WHERE lesson_id=?",(lid,)).fetchall()
    comments=c.execute("""SELECT c.*,u.full_name FROM comments c JOIN users u ON u.id=c.user_id
                          WHERE c.lesson_id=? ORDER BY c.created_at DESC""",(lid,)).fetchall()
    saved=c.execute("SELECT 1 FROM saved_lessons WHERE user_id=? AND lesson_id=?",(current_user()["id"],lid)).fetchone()
    c.close()
    body=f"""<div class="hero"><span class="badge">{l["category"] or "Lesson"}</span><h1>{l["title"]}</h1><h3>{l["title_am"] or ""}</h3><p>{l["bible_reference"] or ""}</p></div><main>
    <div class="card"><span class="muted">By {l["author"]}</span><p style="line-height:1.8;white-space:pre-wrap">{l["content"] or "No text content."}</p>
    <form method="post" action="/lesson/{lid}/save"><button>{"🔖 Remove saved" if saved else "🔖 Save lesson"}</button></form></div>"""
    if audio:
        body+="<div class='card'><h3>🎧 Audio</h3>"
        for x in audio: body+=f'<p>{x["title"]}</p><audio controls style="width:100%" src="{x["file_path"]}"></audio>'
        body+="</div>"
    if videos:
        body+="<div class='card'><h3>🎥 Videos</h3>"
        for x in videos: body+=f'<p><a target="_blank" href="{x["video_url"] or x["file_path"]}">{x["title"]}</a></p>'
        body+="</div>"
    if links:
        body+="<div class='card'><h3>🔗 Links</h3>"
        for x in links: body+=f'<p><a target="_blank" href="{x["url"]}">{x["platform"]}: {x["title"] or x["url"]}</a></p>'
        body+="</div>"
    body+="<div class='card'><h3>💬 Discussion | ውይይት</h3><form method='post' action='/lesson/"+str(lid)+"/comment'><textarea name='comment' placeholder='Write a comment | አስተያየት ጻፍ...' required></textarea><button>Post | ላክ</button></form>"
    for x in comments: body+=f'<div style="padding:10px 0;border-top:1px solid #eee"><b>{x["full_name"]}</b><p>{x["comment"]}</p><span class="muted">{x["created_at"]}</span></div>'
    body+="</div></main>"; return page(body)

@app.post("/lesson/<int:lid>/save")
def save(lid):
    if not current_user(): return redirect("/login")
    c=conn(); e=c.execute("SELECT 1 FROM saved_lessons WHERE user_id=? AND lesson_id=?",(current_user()["id"],lid)).fetchone()
    if e: c.execute("DELETE FROM saved_lessons WHERE user_id=? AND lesson_id=?",(current_user()["id"],lid))
    else: c.execute("INSERT INTO saved_lessons(user_id,lesson_id) VALUES (?,?)",(current_user()["id"],lid))
    c.commit(); c.close(); return redirect(f"/lesson/{lid}")

@app.post("/lesson/<int:lid>/comment")
def comment(lid):
    if not current_user(): return redirect("/login")
    txt=request.form.get("comment","").strip()
    if txt:
        c=conn(); c.execute("INSERT INTO comments(lesson_id,user_id,comment) VALUES (?,?,?)",(lid,current_user()["id"],txt)); c.commit(); c.close()
    return redirect(f"/lesson/{lid}")

@app.route("/saved")
def saved():
    if not current_user(): return redirect("/login")
    c=conn(); rows=c.execute("""SELECT l.*,u.full_name author,c.name_en category FROM saved_lessons s JOIN lessons l ON l.id=s.lesson_id
                                JOIN users u ON u.id=l.author_id LEFT JOIN categories c ON c.id=l.category_id
                                WHERE s.user_id=? ORDER BY s.saved_at DESC""",(current_user()["id"],)).fetchall(); c.close()
    body='<div class="hero"><h1>🔖 Saved Lessons</h1><p>የተቀመጡ ትምህርቶች</p></div><main>'
    for l in rows: body+=f'<a href="/lesson/{l["id"]}"><div class="card"><span class="badge">{l["category"] or "Lesson"}</span><h3>{l["title"]}</h3><p>{l["title_am"] or ""}</p></div></a>'
    body+="</main>"; return page(body)

@app.route("/profile")
def profile():
    if not current_user(): return redirect("/login")
    u=current_user(); c=conn()
    s=c.execute("SELECT COUNT(*) FROM saved_lessons WHERE user_id=?",(u["id"],)).fetchone()[0]
    m=c.execute("SELECT COUNT(*) FROM comments WHERE user_id=?",(u["id"],)).fetchone()[0]; c.close()
    admin=f'<p><a href="/admin">⚙️ Admin Panel | የአስተዳዳሪ ገጽ</a></p>' if u["role_name"]=="Admin" else ""
    body=f'<div class="hero"><h1>👤 Profile</h1><p>መገለጫ</p></div><main><div class="card"><h3>{u["full_name"]}</h3><p>@{u["username"]}</p><p>Role: <b>{u["role_name"]}</b></p>{admin}<a href="/logout">Sign out | ውጣ</a></div><div class="row"><div class="card"><b>{s}</b><br><span class="muted">Saved</span></div><div class="card"><b>{m}</b><br><span class="muted">Comments</span></div></div></main>'
    return page(body)

@app.route("/admin")
def admin():
    u=current_user()
    if not u or u["role_name"]!="Admin": return "Admin access required",403
    c=conn(); rows=c.execute("""SELECT u.username,u.full_name,u.status,r.name role_name FROM users u
                                JOIN roles r ON r.id=u.role_id ORDER BY u.id""").fetchall(); c.close()
    body='<div class="hero"><h1>⚙️ Admin Panel</h1><p>Youth account list | የወጣቶች መረጃ</p></div><main>'
    for x in rows: body+=f'<div class="card"><b>{x["full_name"]}</b><br><span class="muted">@{x["username"]} · {x["role_name"]} · {x["status"]}</span></div>'
    body+="</main>"; return page(body)

@app.route("/health")
def health():
    return {"status":"ok","app":"church-youth-bible-study"}

init_db()

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
