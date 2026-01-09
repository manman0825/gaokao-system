# ==================== 1. 依赖 ====================
import os
import math
import re
import bcrypt
import pandas as pd
from flask import Flask, request, redirect, session, jsonify, url_for
from flask_sqlalchemy import SQLAlchemy

# ==================== 2. 基础配置 ====================
DB_FILE = '/tmp/gaokao.db'
XLSX    = '福建2025年专家版大数据.xlsx'
TXT     = '填报指南.txt'
TIP_FILE= '志愿技巧.txt'          # 新增技巧文件

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_FILE}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-123')
db = SQLAlchemy(app)

# ==================== 3. 数据模型（完全对齐文档）=======
class User(db.Model):
    __tablename__ = 'users'
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)   # 已存 bcrypt 密文
    role     = db.Column(db.String(20), default='user')   # user/admin

class AdmissionRecord(db.Model):
    __tablename__ = 'admission_records'
    id          = db.Column(db.Integer, primary_key=True)
    year        = db.Column(db.String(10))
    batch       = db.Column(db.String(50))
    category    = db.Column(db.String(50))   # 物理类/历史类
    requirement = db.Column(db.String(100))  # 选科要求
    college_name= db.Column(db.String(100), index=True)
    college_code= db.Column(db.String(20))
    college_info= db.Column(db.Text)
    major_name  = db.Column(db.String(100), index=True)
    major_code  = db.Column(db.String(20))
    major_info  = db.Column(db.Text)
    min_score   = db.Column(db.Integer)
    min_rank    = db.Column(db.Integer)
    avg_score   = db.Column(db.Integer)
    max_score   = db.Column(db.Integer)
    tuition     = db.Column(db.String(50))
    city        = db.Column(db.String(50))
    probability = db.Column(db.Integer)      # 录取概率（0-100），后台计算

# ==================== 4. 工具函数 ====================
def calc_probability(user_score, min_s, avg_s):
    """简单概率模型：文档要求±25分+三段颜色"""
    if not min_s or not avg_s:
        return 0
    gap = user_score - avg_s
    if gap >= 25:
        return 95
    if gap >= 0:
        return 70
    if gap >= -25:
        return 40
    return 10

def set_prob(records, user_score):
    """给一组记录补算/补写 probability，永不出现 None"""
    for r in records:
        # 如果拿不到有效分数，直接给 0，避免 None
        r.probability = calc_probability(
            user_score,
            r.min_score or 0,
            r.avg_score or r.min_score or 0
        )
    db.session.commit()
    return records

def hash_pwd(pwd):
    return bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()

def check_pwd(pwd, hashed):
    return bcrypt.checkpw(pwd.encode(), hashed.encode())

# ==================== 5. 应用初始化（gunicorn 安全）=======
def create_app():
    with app.app_context():
        db.create_all()
        # 默认账号
        if User.query.count() == 0:
            db.session.add(User(username='admin', password=hash_pwd('123456'), role='admin'))
            db.session.add(User(username='user',  password=hash_pwd('123456'), role='user'))
            db.session.commit()
        # 空库自动导 Excel
        if AdmissionRecord.query.count() == 0 and os.path.exists(XLSX):
            df = pd.read_excel(XLSX, header=2, engine='openpyxl')
            for _, row in df.iterrows():
                if pd.isna(row.get('院校名称')): continue
                min_s = int(row['最低分1']) if '最低分1' in row and pd.notna(row['最低分1']) else None
                avg_s = int(row['平均分']) if '平均分' in row and pd.notna(row['平均分']) else min_s
                rec = AdmissionRecord(
                    year=str(row.get('年份', '2025')),
                    batch=row.get('批次', ''),
                    category=row.get('科类', ''),
                    requirement=row.get('选科要求', ''),
                    college_name=row['院校名称'],
                    college_code=str(row.get('院校代码', '')),
                    college_info=str(row.get('院校基础信息', '')),
                    major_name=row.get('专业名称', ''),
                    major_code=str(row.get('专业代码', '')),
                    major_info=str(row.get('专业基础信息', '')),
                    min_score=min_s,
                    min_rank=int(row['最低位次']) if '最低位次' in row and pd.notna(row['最低位次']) else None,
                    avg_score=avg_s,
                    max_score=int(row['最高分']) if '最高分' in row and pd.notna(row['最高分']) else None,
                    tuition=str(row.get('学费', '')),
                    city=str(row.get('城市', ''))
                )
                db.session.add(rec)
            db.session.commit()
    return app

create_app()

# ==================== 6. 路由 =================================================
from flask import render_template_string as _r

def bs_html(content):
    """套 Bootstrap5 外壳"""
    return _r('''
<!doctype html><html lang="zh">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>福建高考志愿系统</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body class="bg-light">
<nav class="navbar navbar-dark bg-primary">
  <div class="container-fluid">
    <a class="navbar-brand" href="/">福建高考志愿系统</a>
    <div>
      {% if session.username %}
        <span class="text-white me-3">{{ session.username }} ({{ session.role }})</span>
        <a class="btn btn-sm btn-outline-light" href="/logout">退出</a>
      {% else %}
        <a class="btn btn-sm btn-outline-light" href="/login">登录</a>
      {% endif %}
      <a class="btn btn-sm btn-outline-light ms-2" href="/colleges">院校库</a>
      <a class="btn btn-sm btn-outline-light ms-2" href="/majors">专业库</a>
      <a class="btn btn-sm btn-outline-light ms-2" href="/skill">填报技巧</a>
    </div>
  </div>
</nav>
<div class="container mt-4">''' + content + '''</div>
</body></html>''', session=session)

@app.route('/')
def index():
    return bs_html('''
<h2>欢迎使用福建高考志愿填报系统</h2>
<div class="d-grid gap-2 d-md-flex">
  <a class="btn btn-primary me-2" href="/register">用户注册</a>
  <a class="btn btn-success me-2" href="/login">学生/家长登录</a>
  <a class="btn btn-warning me-2" href="/admin/login">管理员登录</a>
  <a class="btn btn-info" href="/query">直接查询</a>
</div>''')

# ---------- 注册 ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u, p = request.form['username'], request.form['password']
        if User.query.filter_by(username=u).first():
            return bs_html('<div class="alert alert-danger">用户名已存在</div>')
        db.session.add(User(username=u, password=hash_pwd(p), role='user'))
        db.session.commit()
        return bs_html('<div class="alert alert-success">注册成功，<a href="/login">去登录</a></div>')
    return bs_html('''
<h4>用户注册</h4>
<form method="post">
  <div class="mb-3"><label>用户名</label><input class="form-control" name="username" required></div>
  <div class="mb-3"><label>密码</label><input type="password" class="form-control" name="password" required></div>
  <button class="btn btn-primary">注册</button>
</form>''')

# ---------- 登录 ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form['username'], request.form['password']
        user = User.query.filter_by(username=u).first()
        if user and check_pwd(p, user.password):
            session['username'] = u
            session['role'] = user.role
            return redirect('/query')
        return bs_html('<div class="alert alert-danger">账号或密码错误</div>')
    return bs_html('''
<h4>登录</h4>
<form method="post">
  <div class="mb-3"><label>用户名</label><input class="form-control" name="username" required></div>
  <div class="mb-3"><label>密码</label><input type="password" class="form-control" name="password" required></div>
  <button class="btn btn-primary">登录</button>
</form>''')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ---------- 查询（已支持 GET/POST 组合过滤） ----------
@app.route('/query', methods=['GET', 'POST'])
def query():
    # 统一取参数，POST 优先，GET 兜底
    user_score = int((request.form if request.method=='POST' else request.args).get('score', 0))
    college    = (request.form if request.method=='POST' else request.args).get('college', '').strip()
    major      = (request.form if request.method=='POST' else request.args).get('major', '').strip()
    category   = (request.form if request.method=='POST' else request.args).get('category', '').strip()
    requirement= (request.form if request.method=='POST' else request.args).get('requirement', '').strip()

    q = AdmissionRecord.query
    if college:     q = q.filter(AdmissionRecord.college_name.contains(college))
    if major:       q = q.filter(AdmissionRecord.major_name.contains(major))
    if category:    q = q.filter(AdmissionRecord.category == category)
    if requirement: q = q.filter(AdmissionRecord.requirement.contains(requirement))

    records = q.all()
    if user_score:               # 有分数才算概率
        records = set_prob(records, user_score)

    # 生成表格
    tbl = '\n'.join(f'''
        <tr>
          <td><a href="/college/{r.college_name}">{r.college_name}</a></td>
          <td><a href="/major/{r.major_name}">{r.major_name}</a></td>
          <td>{r.category}</td><td>{r.min_score or ''}</td><td>{r.avg_score or ''}</td>
          <td><span class="badge {"bg-success" if (r.probability or 0)>80 else "bg-warning" if (r.probability or 0)>40 else "bg-danger"}">{r.probability}%</span></td>
        </tr>''' for r in records)

    # 返回页面（GET/POST 同模板）
    return bs_html(f'''
<h4>志愿查询</h4>
<form method="get" class="row g-3 mb-3">   <!-- 改用 GET，方便分享 -->
  <div class="col-md-2"><label>高考分数</label><input type="number" class="form-control" name="score" value="{user_score or ''}"></div>
  <div class="col-md-2"><label>院校名称</label><input class="form-control" name="college" value="{college}"></div>
  <div class="col-md-2"><label>专业名称</label><input class="form-control" name="major" value="{major}"></div>
  <div class="col-md-2"><label>科类</label>
      <select class="form-select" name="category"><option value="">全部</option><option{" selected" if category=="物理类" else ""}>物理类</option><option{" selected" if category=="历史类" else ""}>历史类</option></select></div>
  <div class="col-md-2"><label>选科要求</label><input class="form-control" name="requirement" value="{requirement}" placeholder="如 化"></div>
  <div class="col-md-2 align-self-end"><button class="btn btn-primary">查询</button></div>
</form>
{('<table class="table table-bordered table-sm"><thead class="table-light"><tr><th>院校</th><th>专业</th><th>科类</th><th>最低分</th><th>平均分</th><th>录取概率</th></tr></thead><tbody>' + tbl + '</tbody></table>') if records else '<div class="alert alert-info">暂无数据，请调整条件</div>'}''')

# ---------- 智能分析报告 ----------
@app.route('/analysis')
def analysis():
    score   = int(request.args.get('score', 0))
    college = request.args.get('college', '')
    major   = request.args.get('major', '')
    category= request.args.get('category', '')
    q = AdmissionRecord.query
    if college:  q = q.filter(AdmissionRecord.college_name.contains(college))
    if major:    q = q.filter(AdmissionRecord.major_name.contains(major))
    if category: q = q.filter(AdmissionRecord.category == category)
    records = q.all()
    # 概率区间 ±25
    data = []
    for r in records:
        p = calc_probability(score, r.min_score, r.avg_score or r.min_score)
        if (score - 25) <= (r.avg_score or r.min_score or 0) <= (score + 25):
            data.append({'school': r.college_name, 'prob': p})
    data = sorted(data, key=lambda x: x['prob'], reverse=True)[:30]
    chart_data = {
        'labels': [d['school'] for d in data],
        'datasets': [{
            'label': '录取概率',
            'data': [d['prob'] for d in data],
            'backgroundColor': ['#28a745' if v > 80 else '#ffc107' if v > 40 else '#dc3545' for v in [d['prob'] for d in data]]
        }]
    }
    return bs_html(f'''
<h4>智能分析报告</h4>
<p>您的分数：<strong>{score}</strong> 分</p>
<p>分析范围：分数±25 分内的院校</p>
<canvas id="probChart" height="100"></canvas>
<script>
var ctx = document.getElementById('probChart').getContext('2d');
new Chart(ctx, {{type: 'bar', data: {chart_data},
  options: {{ indexAxis: 'y', plugins: {{tooltip: {{ callbacks: {{ label: function(ctx) {{ return '概率: ' + ctx.parsed.x + '%' }} }} }} }} }}
}});
</script>
<a class="btn btn-secondary" href="/query">返回查询</a>''')

# ---------- 填报指南 ----------
@app.route('/guide')
def guide():
    if not os.path.exists(TXT):
        return bs_html('<div class="alert alert-warning">暂无填报指南</div>')
    with open(TXT, encoding='utf-8') as f:
        txt = f.read().replace('\n', '<br>')
    return bs_html(f'<h4>填报指南</h4><div class="border p-3">{txt}</div><a class="btn btn-secondary mt-3" href="/query">返回</a>')

# ---------- 志愿填报技巧 ----------
@app.route('/skill')
def skill():
    if not os.path.exists(TIP_FILE):
        return bs_html('<div class="alert alert-warning">暂无志愿技巧</div>')
    with open(TIP_FILE, encoding='utf-8') as f:
        txt = f.read().replace('\n', '<br>')
    return bs_html(f'<h4>志愿填报技巧</h4><div class="border p-3">{txt}</div><a class="btn btn-secondary mt-3" href="/query">返回</a>')

# ---------- 院校库 ----------
@app.route('/colleges')
def colleges():
    kw = request.args.get('search', '').strip()
    q = db.session.query(AdmissionRecord.college_name,
                         AdmissionRecord.college_code,
                         AdmissionRecord.city,
                         db.func.count(AdmissionRecord.id).label('cnt'))\
                  .group_by(AdmissionRecord.college_name)
    if kw:
        q = q.filter(AdmissionRecord.college_name.contains(kw))
    rows = q.all()
    return bs_html(f'''
<h4>院校库</h4>
<form class="row g-2 mb-3">
  <div class="col-auto"><input class="form-control" name="search" placeholder="院校名称" value="{kw}"></div>
  <div class="col-auto"><button class="btn btn-primary">搜索</button></div>
</form>
<table class="table table-bordered table-sm">
  <thead class="table-light"><tr><th>院校名称</th><th>院校代码</th><th>所在城市</th><th>招生专业数</th></tr></thead>
  <tbody>''' + '\n'.join(f'''<tr>
      <td><a href="/college/{r.college_name}">{r.college_name}</a></td>
      <td>{r.college_code or ''}</td><td>{r.city or ''}</td><td>{r.cnt}</td>
    </tr>''' for r in rows) + '''
</tbody></table>''')

# ---------- 专业库 ----------
@app.route('/majors')
def majors():
    kw = request.args.get('search', '').strip()
    q = db.session.query(AdmissionRecord.major_name,
                         AdmissionRecord.major_code,
                         db.func.count(AdmissionRecord.id).label('cnt'))\
                  .group_by(AdmissionRecord.major_name)
    if kw:
        q = q.filter(AdmissionRecord.major_name.contains(kw))
    rows = q.all()
    return bs_html(f'''
<h4>专业库</h4>
<form class="row g-2 mb-3">
  <div class="col-auto"><input class="form-control" name="search" placeholder="专业名称" value="{kw}"></div>
  <div class="col-auto"><button class="btn btn-primary">搜索</button></div>
</form>
<table class="table table-bordered table-sm">
  <thead class="table-light"><tr><th>专业名称</th><th>专业代码</th><th>开设院校数</th></tr></thead>
  <tbody>''' + '\n'.join(f'''<tr>
      <td><a href="/major/{r.major_name}">{r.major_name}</a></td>
      <td>{r.major_code or ''}</td><td>{r.cnt}</td>
    </tr>''' for r in rows) + '''
</tbody></table>''')

# ---------- 院校详情页 ----------
@app.route('/college/<path:name>')
def college_detail(name):
    c = AdmissionRecord.query.filter_by(college_name=name).first_or_404()
    # 把同一个学校的所有专业拉出来
    majors = AdmissionRecord.query.filter_by(college_name=name).all()
    return bs_html(f'''
<h4>{name} 介绍</h4>
<div class="card mb-4">
  <div class="card-body">
    <h5>基本信息</h5>
    <p><strong>院校代码：</strong>{c.college_code or ''}</p>
    <p><strong>所在城市：</strong>{c.city or ''}</p>
    <p><strong>院校标签：</strong>{c.college_info or ''}</p>
  </div>
</div>
<h5>招生专业（{len(majors)} 个）</h5>
<table class="table table-bordered table-sm">
  <thead class="table-light"><tr><th>专业</th><th>科类</th><th>选科</th><th>最低分</th><th>平均分</th></tr></thead>
  <tbody>''' + '\n'.join(f'''<tr>
      <td><a href="/major/{m.major_name}">{m.major_name}</a></td><td>{m.category}</td><td>{m.requirement}</td>
      <td>{m.min_score or ''}</td><td>{m.avg_score or ''}</td>
    </tr>''' for m in majors) + '''
</tbody></table>
<a class="btn btn-secondary" href="/colleges">返回院校库</a>''')

# ---------- 专业详情页 ----------
@app.route('/major/<path:name>')
def major_detail(name):
    m = AdmissionRecord.query.filter_by(major_name=name).first_or_404()
    # 把开这个专业的所有学校拉出来
    schools = AdmissionRecord.query.filter_by(major_name=name).all()
    return bs_html(f'''
<h4>{name} 介绍</h4>
<div class="card mb-4">
  <div class="card-body">
    <h5>基本信息</h5>
    <p><strong>专业代码：</strong>{m.major_code or ''}</p>
    <p><strong>专业简介：</strong>{m.major_info or ''}</p>
  </div>
</div>
<h5>开设院校（{len(schools)} 所）</h5>
<table class="table table-bordered table-sm">
  <thead class="table-light"><tr><th>院校</th><th>科类</th><th>选科</th><th>最低分</th><th>平均分</th></tr></thead>
  <tbody>''' + '\n'.join(f'''<tr>
      <td><a href="/college/{s.college_name}">{s.college_name}</a></td><td>{s.category}</td><td>{s.requirement}</td>
      <td>{s.min_score or ''}</td><td>{s.avg_score or ''}</td>
    </tr>''' for s in schools) + '''
</tbody></table>
<a class="btn btn-secondary" href="/majors">返回专业库</a>''')

# ==================== 7. 管理员后台（完整） ====================
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        u, p = request.form['username'], request.form['password']
        user = User.query.filter_by(username=u, role='admin').first()
        if user and check_pwd(p, user.password):
            session['username'] = u
            session['role'] = 'admin'
            return redirect('/admin/dashboard')
        return bs_html('<div class="alert alert-danger">管理员账号或密码错误</div>')
    return bs_html('''
<h4>管理员登录</h4>
<form method="post">
  <div class="mb-3"><label>账号</label><input class="form-control" name="username" required></div>
  <div class="mb-3"><label>密码</label><input type="password" class="form-control" name="password" required></div>
  <button class="btn btn-primary">登录</button>
</form>''')

@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect('/admin/login')
    return bs_html(f'''
<h4>管理后台</h4>
<div class="row">
  <div class="col-md-4">
    <div class="card">
      <div class="card-body">
        <h5 class="card-title">用户管理</h5>
        <p class="card-text">共 {User.query.count()} 个账号</p>
        <a href="/admin/users" class="btn btn-primary">进入</a>
      </div>
    </div>
  </div>
  <div class="col-md-4">
    <div class="card">
      <div class="card-body">
        <h5 class="card-title">录取数据管理</h5>
        <p class="card-text">共 {AdmissionRecord.query.count()} 条记录</p>
        <a href="/admin/data" class="btn btn-primary">进入</a>
      </div>
    </div>
  </div>
</div>''')

# ---------- 用户管理 ----------
@app.route('/admin/users')
def admin_users():
    if session.get('role') != 'admin':
        return redirect('/admin/login')
    users = User.query.all()
    return bs_html(f'''
<h4>用户列表</h4>
<a class="btn btn-success mb-3" href="/admin/user/add">+ 添加新用户</a>
<table class="table table-bordered table-sm">
  <thead class="table-light"><tr><th>ID</th><th>用户名</th><th>角色</th><th>操作</th></tr></thead>
  <tbody>''' + '\n'.join(f'''
    <tr>
      <td>{u.id}</td><td>{u.username}</td><td>{u.role}</td>
      <td>
        <a class="btn btn-sm btn-warning" href="/admin/user/edit/{u.id}">编辑</a>
        <a class="btn btn-sm btn-danger" href="/admin/user/del/{u.id}" onclick="return confirm('确定删除吗？')">删除</a>
      </td>
    </tr>''' for u in users) + '''
</tbody></table>''')

@app.route('/admin/user/add', methods=['GET', 'POST'])
def admin_user_add():
    if session.get('role') != 'admin':
        return redirect('/admin/login')
    if request.method == 'POST':
        u, p, r = request.form['username'], request.form['password'], request.form['role']
        if User.query.filter_by(username=u).first():
            return bs_html('<div class="alert alert-danger">用户名已存在</div>')
        db.session.add(User(username=u, password=hash_pwd(p), role=r))
        db.session.commit()
        return redirect('/admin/users')
    return bs_html('''
<h4>添加用户</h4>
<form method="post">
  <div class="mb-3"><label>用户名</label><input class="form-control" name="username" required></div>
  <div class="mb-3"><label>密码</label><input type="password" class="form-control" name="password" required></div>
  <div class="mb-3"><label>角色</label>
    <select class="form-select" name="role"><option value="user">学生/家长</option><option value="admin">管理员</option></select></div>
  <button class="btn btn-primary">创建</button>
</form>''')

@app.route('/admin/user/edit/<int:uid>', methods=['GET', 'POST'])
def admin_user_edit(uid):
    if session.get('role') != 'admin':
        return redirect('/admin/login')
    user = User.query.get_or_404(uid)
    if request.method == 'POST':
        user.password = hash_pwd(request.form['password'])
        user.role     = request.form['role']
        db.session.commit()
        return redirect('/admin/users')
    return bs_html(f'''
<h4>编辑用户</h4>
<form method="post">
  <div class="mb-3"><label>新密码</label><input type="password" class="form-control" name="password" required></div>
  <div class="mb-3"><label>角色</label>
    <select class="form-select" name="role"><option value="user" {"selected" if user.role=="user" else ""}>学生/家长</option><option value="admin" {"selected" if user.role=="admin" else ""}>管理员</option></select></div>
  <button class="btn btn-primary">保存</button>
</form>''')

@app.route('/admin/user/del/<int:uid>')
def admin_user_del(uid):
    if session.get('role') != 'admin':
        return redirect('/admin/login')
    User.query.filter_by(id=uid).delete()
    db.session.commit()
    return redirect('/admin/users')

# ---------- 录取数据管理 ----------
@app.route('/admin/data')
def admin_data():
    if session.get('role') != 'admin':
        return redirect('/admin/login')
    keyword = request.args.get('search', '')
    page = int(request.args.get('page', 1))
    q = AdmissionRecord.query
    if keyword:
        q = q.filter(AdmissionRecord.college_name.contains(keyword))
    records = q.paginate(page=page, per_page=20, error_out=False)
    return bs_html(f'''
<h4>录取数据管理</h4>
<form class="row g-2 mb-3">
  <div class="col-auto"><input class="form-control" name="search" placeholder="院校名称" value="{keyword}"></div>
  <div class="col-auto"><button class="btn btn-primary">搜索</button></div>
</form>
<a class="btn btn-success mb-3" href="/admin/data/add">+ 新增数据</a>
<table class="table table-bordered table-sm">
  <thead class="table-light"><tr>
    <th>ID</th><th>院校</th><th>专业</th><th>科类</th><th>最低分</th><th>操作</th>
  </tr></thead>
  <tbody>''' + '\n'.join(f'''
    <tr>
      <td>{r.id}</td><td>{r.college_name}</td><td>{r.major_name}</td><td>{r.category}</td><td>{r.min_score or ""}</td>
      <td>
        <a class="btn btn-sm btn-warning" href="/admin/data/edit/{r.id}">编辑</a>
        <a class="btn btn-sm btn-danger" href="/admin/data/del/{r.id}" onclick="return confirm('确定删除吗？')">删除</a>
      </td>
    </tr>''' for r in records.items) + f'''
</tbody></table>
<nav><ul class="pagination">
  <li class="page-item {"disabled" if not records.has_prev else ""}">
    <a class="page-link" href="{url_for('admin_data', search=keyword, page=records.prev_num) if records.has_prev else "#"}">上一页</a>
  </li>
  <li class="page-item {"disabled" if not records.has_next else ""}">
    <a class="page-link" href="{url_for('admin_data', search=keyword, page=records.next_num) if records.has_next else "#"}">下一页</a>
  </li>
</ul></nav>''')

@app.route('/admin/data/add', methods=['GET', 'POST'])
def admin_data_add():
    if session.get('role') != 'admin':
        return redirect('/admin/login')
    if request.method == 'POST':
        f = request.form
        r = AdmissionRecord(
            year=f['year'], batch=f['batch'], category=f['category'], requirement=f['requirement'],
            college_name=f['college_name'], college_code=f['college_code'], college_info=f['college_info'],
            major_name=f['major_name'], major_code=f['major_code'], major_info=f['major_info'],
            min_score=int(f['min_score']) if f['min_score'] else None,
            min_rank=int(f['min_rank']) if f['min_rank'] else None,
            avg_score=int(f['avg_score']) if f['avg_score'] else None,
            max_score=int(f['max_score']) if f['max_score'] else None,
            tuition=f['tuition'], city=f['city']
        )
        db.session.add(r)
        db.session.commit()
        return redirect('/admin/data')
    return bs_html('''
<h4>新增录取数据</h4>
<form method="post">
  <div class="row g-2">
    <div class="col-md-2"><label>年份</label><input class="form-control" name="year" value="2025"></div>
    <div class="col-md-2"><label>批次</label><input class="form-control" name="batch"></div>
    <div class="col-md-2"><label>科类</label><input class="form-control" name="category"></div>
    <div class="col-md-2"><label>选科要求</label><input class="form-control" name="requirement"></div>
    <div class="col-md-4"><label>院校名称</label><input class="form-control" name="college_name" required></div>
    <div class="col-md-2"><label>院校代码</label><input class="form-control" name="college_code"></div>
    <div class="col-md-4"><label>专业名称</label><input class="form-control" name="major_name" required></div>
    <div class="col-md-2"><label>专业代码</label><input class="form-control" name="major_code"></div>
    <div class="col-md-6"><label>院校信息</label><textarea class="form-control" name="college_info"></textarea></div>
    <div class="col-md-6"><label>专业信息</label><textarea class="form-control" name="major_info"></textarea></div>
    <div class="col-md-2"><label>最低分</label><input type="number" class="form-control" name="min_score"></div>
    <div class="col-md-2"><label>最低位次</label><input type="number" class="form-control" name="min_rank"></div>
    <div class="col-md-2"><label>平均分</label><input type="number" class="form-control" name="avg_score"></div>
    <div class="col-md-2"><label>最高分</label><input type="number" class="form-control" name="max_score"></div>
    <div class="col-md-2"><label>学费</label><input class="form-control" name="tuition"></div>
    <div class="col-md-2"><label>城市</label><input class="form-control" name="city"></div>
  </div>
  <button class="btn btn-primary mt-3">提交</button>
</form>''')

@app.route('/admin/data/edit/<int:rid>', methods=['GET', 'POST'])
def admin_data_edit(rid):
    if session.get('role') != 'admin':
        return redirect('/admin/login')
    r = AdmissionRecord.query.get_or_404(rid)
    if request.method == 'POST':
        f = request.form
        r.year        = f['year']; r.batch     = f['batch']; r.category  = f['category']; r.requirement = f['requirement']
        r.college_name= f['college_name']; r.college_code = f['college_code']; r.college_info = f['college_info']
        r.major_name  = f['major_name']; r.major_code   = f['major_code'];   r.major_info   = f['major_info']
        r.min_score   = int(f['min_score']) if f['min_score'] else None
        r.min_rank    = int(f['min_rank'])  if f['min_rank']  else None
        r.avg_score   = int(f['avg_score']) if f['avg_score'] else None
        r.max_score   = int(f['max_score']) if f['max_score'] else None
        r.tuition     = f['tuition']; r.city = f['city']
        db.session.commit()
        return redirect('/admin/data')
    return bs_html(f'''
<h4>编辑数据</h4>
<form method="post">
  <div class="row g-2">
    <div class="col-md-2"><label>年份</label><input class="form-control" name="year" value="{r.year}"></div>
    <div class="col-md-2"><label>批次</label><input class="form-control" name="batch" value="{r.batch}"></div>
    <div class="col-md-2"><label>科类</label><input class="form-control" name="category" value="{r.category}"></div>
    <div class="col-md-2"><label>选科要求</label><input class="form-control" name="requirement" value="{r.requirement or ''}"></div>
    <div class="col-md-4"><label>院校名称</label><input class="form-control" name="college_name" value="{r.college_name}" required></div>
    <div class="col-md-2"><label>院校代码</label><input class="form-control" name="college_code" value="{r.college_code or ''}"></div>
    <div class="col-md-4"><label>专业名称</label><input class="form-control" name="major_name" value="{r.major_name}" required></div>
    <div class="col-md-2"><label>专业代码</label><input class="form-control" name="major_code" value="{r.major_code or ''}"></div>
    <div class="col-md-6"><label>院校信息</label><textarea class="form-control" name="college_info">{r.college_info or ''}</textarea></div>
    <div class="col-md-6"><label>专业信息</label><textarea class="form-control" name="major_info">{r.major_info or ''}</textarea></div>
    <div class="col-md-2"><label>最低分</label><input type="number" class="form-control" name="min_score" value="{r.min_score or ''}"></div>
    <div class="col-md-2"><label>最低位次</label><input type="number" class="form-control" name="min_rank" value="{r.min_rank or ''}"></div>
    <div class="col-md-2"><label>平均分</label><input type="number" class="form-control" name="avg_score" value="{r.avg_score or ''}"></div>
    <div class="col-md-2"><label>最高分</label><input type="number" class="form-control" name="max_score" value="{r.max_score or ''}"></div>
    <div class="col-md-2"><label>学费</label><input class="form-control" name="tuition" value="{r.tuition or ''}"></div>
    <div class="col-md-2"><label>城市</label><input class="form-control" name="city" value="{r.city or ''}"></div>
  </div>
  <button class="btn btn-primary mt-3">保存</button>
</form>''')

@app.route('/admin/data/del/<int:rid>')
def admin_data_del(rid):
    if session.get('role') != 'admin':
        return redirect('/admin/login')
    AdmissionRecord.query.filter_by(id=rid).delete()
    db.session.commit()
    return redirect('/admin/data')

# ==================== 8. 启动（仅本地） ====================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

