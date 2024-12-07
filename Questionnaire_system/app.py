from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask import send_from_directory
from database import db, User, Survey, Question, Option, Response, SurveyResponse, Feedback, FeedbackReply
from werkzeug.security import generate_password_hash, check_password_hash
from io import BytesIO
import os
import qrcode
import base64
from datetime import datetime
from flask_migrate import Migrate

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///survey.db'
app.config['STATIC_FOLDER'] = 'static'
db.init_app(app)
migrate = Migrate(app, db)

@app.route('/')
def index():
    # 直接显示 index 页面，不再检查登录状态
    return render_template('index.html', hide_nav=True)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        
        if role == 'teacher' and request.form['invite_code'] != '123456':
            flash('教师邀请码错误')
            return redirect(url_for('register'))
            
        if User.query.filter_by(username=username).first():
            flash('用户名已存在')
            return redirect(url_for('register'))
            
        if role == 'student':
            student_id = request.form.get('student_id')
            real_name = request.form.get('real_name')
            
            # 验证学号
            if not student_id or len(student_id) != 7 or not student_id.isdigit():
                flash('请输入7位数字的学号')
                return redirect(url_for('register'))
                
            # 验证姓名
            if not real_name:
                flash('请输入真实姓名')
                return redirect(url_for('register'))
                
            # 检查学号是否已被注册
            if User.query.filter_by(student_id=student_id).first():
                flash('该学号已被注册')
                return redirect(url_for('register'))
                
            user = User(
                username=username,
                password=generate_password_hash(password),
                role=role,
                student_id=student_id,
                real_name=real_name
            )
        else:
            user = User(
                username=username,
                password=generate_password_hash(password),
                role=role
            )
            
        db.session.add(user)
        db.session.commit()
        
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['role'] = user.role
            
            # 检查是否有待跳转的页面
            next_page = session.pop('next', None)
            if next_page:
                return redirect(next_page)
            return redirect(url_for('dashboard'))
            
        flash('用户名或密码错误')
    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    if session['role'] == 'teacher':
        surveys = Survey.query.filter_by(teacher_id=session['user_id']).all()
        return render_template('teacher/dashboard.html', surveys=surveys)
    else:
        # 获取所有卷
        surveys = Survey.query.filter_by(is_active=True).all()
        # 获取学生的答卷历史
        responses = SurveyResponse.query.filter_by(student_id=session['user_id']).order_by(SurveyResponse.submitted_at.desc()).all()
        return render_template('student/dashboard.html', 
                             surveys=surveys,
                             responses=responses)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
        
    user = User.query.get_or_404(session['user_id'])
    
    if request.method == 'POST':
        edit_type = request.form.get('edit_type')
        
        if edit_type == 'username':
            # 修改用户名不需要验证密码
            new_username = request.form.get('new_value')
            if new_username:
                # 检查用户名是否已被使用
                if User.query.filter(User.id != user.id, User.username == new_username).first():
                    flash('该用户名已被使用')
                    return redirect(url_for('profile'))
                user.username = new_username
                flash('用户名修改成功')
                db.session.commit()
                return redirect(url_for('profile'))
        
        # 其他修改需要验证密码
        password = request.form.get('password')
        if not password and edit_type not in ['username']:  # 用户名修改不需要密码
            flash('请输入密码')
            return redirect(url_for('profile'))
            
        if password and not check_password_hash(user.password, password):
            flash('密码验证失败')
            return redirect(url_for('profile'))
            
        if edit_type == 'password':
            new_password = request.form.get('new_password')
            if new_password:
                user.password = generate_password_hash(new_password)
                flash('密码修改成功')
        elif edit_type == 'student_id':
            new_student_id = request.form.get('new_value')
            if new_student_id:
                if len(new_student_id) != 7 or not new_student_id.isdigit():
                    flash('请输入7位数字的学号')
                    return redirect(url_for('profile'))
                if User.query.filter(User.id != user.id, User.student_id == new_student_id).first():
                    flash('该学号已被使用')
                    return redirect(url_for('profile'))
                user.student_id = new_student_id
                flash('学号修改成功')
        elif edit_type == 'real_name':
            new_real_name = request.form.get('new_value')
            if new_real_name:
                user.real_name = new_real_name
                flash('姓名修改成功')
                
        db.session.commit()
        return redirect(url_for('profile'))
        
    return render_template('student/profile.html', user=user)

# 教师相关路由
@app.route('/create_survey', methods=['GET', 'POST'])
def create_survey():
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        try:
            # 获取表单数据
            title = request.form.get('title')
            if not title:
                flash('问卷标题不能为空')
                return redirect(url_for('create_survey'))

            # 创建问卷
            survey = Survey(
                title=title,
                teacher_id=session['user_id']
            )
            db.session.add(survey)
            db.session.commit()
            
            # 生成唯一的问卷代码
            survey.generate_code()
            db.session.commit()
            
            # 处理问题和项
            questions = request.form.getlist('questions[]')
            question_types = request.form.getlist('question_types[]')
            
            if not questions:
                flash('至少需要添加一个问题')
                return redirect(url_for('create_survey'))
                
            for i, (q_text, q_type) in enumerate(zip(questions, question_types)):
                if not q_text.strip():
                    continue
                    
                question = Question(
                    survey_id=survey.id,
                    question_text=q_text,
                    question_type=q_type,
                    order=i+1
                )
                db.session.add(question)
                db.session.commit()
                
                if q_type in ['single', 'multiple']:
                    options = request.form.getlist(f'options[{i}][]')
                    for j, opt_text in enumerate(options):
                        if not opt_text.strip():
                            continue
                            
                        option = Option(
                            question_id=question.id,
                            option_text=opt_text.strip(),
                            order=j+1
                        )
                        db.session.add(option)
            
            db.session.commit()
            flash('问卷创建成功！')
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash('创建问卷失败，请检查输入数据是否正确')
            print(f"Error creating survey: {str(e)}")
            return redirect(url_for('create_survey'))
        
    return render_template('teacher/create_survey.html')

@app.route('/edit_survey/<int:survey_id>', methods=['GET', 'POST'])
def edit_survey(survey_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))
        
    original_survey = Survey.query.get_or_404(survey_id)
    if original_survey.teacher_id != session['user_id']:
        flash('您没有权限编辑此问卷')
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        try:
            # 获取表单数据
            title = request.form.get('title')
            questions = request.form.getlist('questions[]')
            question_types = request.form.getlist('question_types[]')
            
            # 检查问卷是否发生变化
            has_changes = False
            
            # 检查标题是否变化
            if title != original_survey.title:
                has_changes = True
                
            # 检查问题数量是否变化
            if len(questions) != len(original_survey.questions):
                has_changes = True
            else:
                # 检查每个问题和选项是否有变化
                original_questions = sorted(original_survey.questions, key=lambda x: x.order)
                for i, (orig_q, new_q_text, new_q_type) in enumerate(zip(original_questions, questions, question_types)):
                    if (orig_q.question_text != new_q_text or 
                        orig_q.question_type != new_q_type):
                        has_changes = True
                        break
                        
                    # 检查选项是否有变化
                    if new_q_type in ['single', 'multiple']:
                        new_options = request.form.getlist(f'options[{i}][]')
                        orig_options = [opt.option_text for opt in sorted(orig_q.options, key=lambda x: x.order)]
                        
                        if len(new_options) != len(orig_options):
                            has_changes = True
                            break
                            
                        for orig_opt, new_opt in zip(orig_options, new_options):
                            if orig_opt != new_opt:
                                has_changes = True
                                break
                                
                    if has_changes:
                        break
            
            if has_changes:
                # 计算这是第几个版本
                base_title = original_survey.title.split(' - ')[0]  # 获取基础标题
                version_count = Survey.query.filter(
                    Survey.title.like(f"{base_title} - 第%版")
                ).count()
                
                new_title = f"{base_title} - 第{version_count + 1}版"
                
                # 创建新问卷
                new_survey = Survey(
                    title=new_title,
                    teacher_id=original_survey.teacher_id,
                    is_active=True if 'is_active' in request.form else False
                )
                db.session.add(new_survey)
                db.session.commit()
                
                # 复制问题和选项
                for i, (q_text, q_type) in enumerate(zip(questions, question_types)):
                    question = Question(
                        survey_id=new_survey.id,
                        question_text=q_text,
                        question_type=q_type,
                        order=i+1
                    )
                    db.session.add(question)
                    db.session.commit()
                    
                    if q_type in ['single', 'multiple']:
                        options = request.form.getlist(f'options[{i}][]')
                        for j, opt_text in enumerate(options):
                            option = Option(
                                question_id=question.id,
                                option_text=opt_text.strip(),
                                order=j+1
                            )
                            db.session.add(option)
                
                db.session.commit()
                flash('问卷已更新，已创建新版本！', 'success')
                return redirect(url_for('dashboard'))
            
            # 如果没有变化，直接更新原问卷的状态
            original_survey.is_active = 'is_active' in request.form
            db.session.commit()
            flash('问卷状态已更新！', 'success')
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash('更新问卷失败，请检查输入数据是否正确')
            print(f"Error updating survey: {str(e)}")
            return redirect(url_for('edit_survey', survey_id=survey_id))
        
    return render_template('teacher/edit_survey.html', survey=original_survey)

@app.route('/view_responses/<int:survey_id>')
def view_responses(survey_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))
        
    survey = Survey.query.get_or_404(survey_id)
    if survey.teacher_id != session['user_id']:
        flash('您没有权限查看此问卷的答卷')
        return redirect(url_for('dashboard'))
        
    # 获取所有的答卷记录
    survey_responses = SurveyResponse.query.filter_by(survey_id=survey_id).all()
    
    return render_template('teacher/view_responses.html', 
                         survey=survey, 
                         survey_responses=survey_responses)

# 学生相关路由
@app.route('/take_survey/<int:survey_id>', methods=['GET', 'POST'])
def take_survey(survey_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
        
    survey = Survey.query.get_or_404(survey_id)
    if not survey.is_active:
        flash('此问卷已关闭')
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        # 创建问卷提交记录
        survey_response = SurveyResponse(
            student_id=session['user_id'],
            survey_id=survey_id
        )
        db.session.add(survey_response)
        db.session.commit()
        
        # 保存每个问题的答案
        for question in survey.questions:
            if question.question_type == 'text':
                text_answer = request.form.get(f'answers[{question.id}]')
                if text_answer:
                    response = Response(
                        student_id=session['user_id'],
                        survey_id=survey_id,
                        question_id=question.id,
                        text_answer=text_answer,
                        survey_response_id=survey_response.id
                    )
                    db.session.add(response)
            elif question.question_type == 'multiple':
                # 处理多选答案
                option_ids = request.form.getlist(f'answers[{question.id}][]')
                for option_id in option_ids:
                    response = Response(
                        student_id=session['user_id'],
                        survey_id=survey_id,
                        question_id=question.id,
                        option_id=int(option_id),
                        survey_response_id=survey_response.id
                    )
                    db.session.add(response)
            else:
                # 处理单选答案
                option_id = request.form.get(f'answers[{question.id}]')
                if option_id:
                    response = Response(
                        student_id=session['user_id'],
                        survey_id=survey_id,
                        question_id=question.id,
                        option_id=int(option_id),
                        survey_response_id=survey_response.id
                    )
                    db.session.add(response)
                
        db.session.commit()
        flash('问卷提交成功！', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('student/take_survey.html', survey=survey)

@app.route('/view_response/<int:response_id>')
def view_response(response_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    survey_response = SurveyResponse.query.get_or_404(response_id)
    survey = survey_response.survey
    
    # 获取该学生对这份问卷的所有回
    responses = Response.query.filter_by(
        survey_response_id=response_id
    ).all()
    
    # 创建答案字典，方便在模板中查找
    answers = {}
    for response in responses:
        if response.question.question_type == 'multiple':
            if response.question_id not in answers:
                answers[response.question_id] = []
            answers[response.question_id].append(response.option_id)
        else:
            answers[response.question_id] = response.option_id if response.option_id else response.text_answer
    
    return render_template('view_response.html',
                           survey=survey,
                           survey_response=survey_response,
                           answers=answers)

@app.route('/survey_statistics/<int:survey_id>')
def survey_statistics(survey_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))
        
    survey = Survey.query.get_or_404(survey_id)
    if survey.teacher_id != session['user_id']:
        flash('您没有权限查看此问卷的统计数据')
        return redirect(url_for('dashboard'))
    
    # 将问题对象转换为字典
    questions_data = [{
        'id': q.id,
        'text': q.question_text,
        'order': q.order
    } for q in sorted(survey.questions, key=lambda x: x.order)]
    
    stats = survey.get_statistics()
    return render_template('teacher/survey_statistics.html', 
                         survey=survey,
                         questions=questions_data,
                         stats=stats)

@app.route('/export_survey/<int:survey_id>')
def export_survey(survey_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))
        
    survey = Survey.query.get_or_404(survey_id)
    if survey.teacher_id != session['user_id']:
        flash('您没有权限导出此问卷的数据')
        return redirect(url_for('dashboard'))
    
    # 生成Excel文件
    wb = survey.to_excel()
    
    # 保存到内存中
    excel_file = BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)
    
    return send_file(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'{survey.title}-统计数据.xlsx'
    )

@app.route('/api/survey_stats/<int:survey_id>')
def api_survey_stats(survey_id):
    """获取问卷统计数据的API接口，用于图表展示"""
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': '未授权'}), 401
        
    survey = Survey.query.get_or_404(survey_id)
    if survey.teacher_id != session['user_id']:
        return jsonify({'error': '无权限'}), 403
    
    stats = survey.get_statistics()
    return jsonify(stats)

@app.route('/delete_survey/<int:survey_id>', methods=['POST'])
def delete_survey(survey_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))
        
    survey = Survey.query.get_or_404(survey_id)
    if survey.teacher_id != session['user_id']:
        flash('您没有权限删除此问卷')
        return redirect(url_for('dashboard'))
        
    try:
        # 删除问卷相关的所有数据
        Response.query.filter_by(survey_id=survey_id).delete()
        SurveyResponse.query.filter_by(survey_id=survey_id).delete()
        for question in survey.questions:
            Option.query.filter_by(question_id=question.id).delete()
        Question.query.filter_by(survey_id=survey_id).delete()
        db.session.delete(survey)
        db.session.commit()
        flash('问卷删除成功！', 'success')
    except Exception as e:
        db.session.rollback()
        flash('删除问卷失败')
        print(f"Error deleting survey: {str(e)}")
        
    return redirect(url_for('dashboard'))

@app.route('/toggle_survey_status/<int:survey_id>', methods=['POST'])
def toggle_survey_status(survey_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))
        
    survey = Survey.query.get_or_404(survey_id)
    if survey.teacher_id != session['user_id']:
        flash('您没有权限修改此问卷')
        return redirect(url_for('dashboard'))
        
    try:
        survey.is_active = not survey.is_active
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('状态更新失败')
        print(f"Error updating survey status: {str(e)}")
        
    return redirect(url_for('dashboard'))

@app.route('/static/images/<path:filename>')
def serve_image(filename):
    try:
        return send_from_directory(os.path.join(app.root_path, 'static', 'images'), filename)
    except Exception as e:
        print(f"Error serving image: {str(e)}")
        return str(e), 500

@app.route('/survey/<string:survey_code>')
def access_survey(survey_code):
    """通过二维码访问问卷"""
    survey = Survey.query.filter_by(code=survey_code).first_or_404()
    
    if not survey.is_active:
        flash('此问卷已关闭')
        return redirect(url_for('index'))
    
    if 'user_id' not in session:
        # 保存目标URL到session
        session['next'] = url_for('access_survey', survey_code=survey_code)
        return redirect(url_for('login'))
        
    if session['role'] != 'student':
        flash('只有学生可以参与问卷调查')
        return redirect(url_for('dashboard'))
        
    return redirect(url_for('take_survey', survey_id=survey.id))

def generate_qr_code(url):
    """生成二维码并返回base64编码的图片"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

@app.route('/generate_qr/<string:survey_code>')
def generate_qr(survey_code):
    """生成问卷的二维码"""
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': '未授权'}), 401
        
    survey = Survey.query.filter_by(code=survey_code).first_or_404()
    if survey.teacher_id != session['user_id']:
        return jsonify({'error': '无权限'}), 403
        
    # 生成问卷的完整URL
    survey_url = url_for('access_survey', survey_code=survey_code, _external=True)
    
    # 生成二维码
    qr_code = generate_qr_code(survey_url)
    
    return jsonify({'qr_code': qr_code})

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    """提交意见反馈"""
    if 'user_id' not in session or session['role'] != 'student':
        return jsonify({'error': '未授权'}), 401
        
    content = request.form.get('content')
    if not content:
        flash('反馈内容不能为空', 'error')
        return redirect(url_for('dashboard'))
        
    feedback = Feedback(
        student_id=session['user_id'],
        content=content
    )
        
    try:
        db.session.add(feedback)
        db.session.commit()
        flash('反馈提交成功！', 'success')
    except Exception as e:
        db.session.rollback()
        flash('反馈提交失败，请稍后重试', 'error')
        print(f"Error submitting feedback: {str(e)}")
        
    return redirect(url_for('dashboard'))

@app.route('/view_feedbacks')
def view_feedbacks():
    """查看意见反馈"""
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))
        
    feedbacks = Feedback.query.order_by(Feedback.created_at.desc()).all()
    return render_template('teacher/view_feedbacks.html', feedbacks=feedbacks)

@app.route('/mark_feedback_as_read/<int:feedback_id>', methods=['POST'])
def mark_feedback_as_read(feedback_id):
    """标记反馈为已读"""
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': '未授权'}), 401
        
    feedback = Feedback.query.get_or_404(feedback_id)
    feedback.status = 'read'
        
    try:
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/student/feedbacks')
def student_feedbacks():
    """学生查看意见反馈页面"""
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    
    feedbacks = Feedback.query.filter_by(student_id=session['user_id']).order_by(Feedback.created_at.desc()).all()
    return render_template('student/feedbacks.html', feedbacks=feedbacks)

@app.route('/reply_feedback/<int:feedback_id>', methods=['POST'])
def reply_feedback(feedback_id):
    """教师回复反馈"""
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': '未授权'}), 401
        
    feedback = Feedback.query.get_or_404(feedback_id)
    reply_content = request.json.get('reply')
    
    if not reply_content:
        return jsonify({'error': '回复内容不能为空'}), 400
    
    try:
        # 创建新的回复记录
        reply = FeedbackReply(
            feedback_id=feedback_id,
            content=reply_content
        )
        # 自动标记为已读
        feedback.status = 'read'
        db.session.add(reply)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'reply_time': reply.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)