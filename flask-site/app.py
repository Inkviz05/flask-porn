from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime
import io
import os
import csv
from sqlalchemy.orm import relationship
import base64
import fitz
import markdown
from bs4 import BeautifulSoup
import pygments
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_for_filename, TextLexer
import chardet
import mammoth
import re
import html

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rooms.db'
app.config['SECRET_KEY'] = 'mysecretkey'
app.config['UPLOAD_FOLDER'] = 'uploads'
db = SQLAlchemy()
db.init_app(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)


class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    reservations = relationship("Reservation", back_populates="room", cascade="all, delete-orphan")


class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    room = relationship("Room", back_populates="reservations")
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('reservations', lazy=True))
    start_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    contract = db.Column(db.Text, nullable=True)


class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)
    mimetype = db.Column(db.String(100), nullable=False)


def init_db():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password='admin', is_admin=True)
        db.session.add(admin)
        db.session.commit()


@app.route('/', methods=['GET'])
def home():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session['user_id'] = user.id
            if user.is_admin:
                return redirect(url_for('admin_panel'))
            return redirect(url_for('main'))
        else:
            flash('Неверные данные для входа!', 'danger')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким именем уже существует!', 'danger')
        else:
            new_user = User(username=username, password=password)
            db.session.add(new_user)
            db.session.commit()
            flash('Регистрация успешна! Вы можете войти.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/main', methods=['GET', 'POST'])
def main():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        room_id = request.form['room_id']
        start_date = request.form['start_date']
        start_time = request.form['start_time']
        duration = request.form['duration']

        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        start_time = datetime.strptime(start_time, '%H:%M').time()

        user_id = session['user_id']
        user = User.query.get(user_id)
        room = Room.query.get(room_id)

        contract_text = f"""
                ДОГОВОР БРОНИРОВАНИЯ № {room.id}

                Пользователь: {user.username}  
                Переговорная комната: {room.name}  
                Адрес: Улица Пушкина 57  

                Дата бронирования: {start_date}  
                Время начала: {start_time}  
                Продолжительность: {duration} минут  

                **Общие условия:**  
                1. Настоящий договор подтверждает факт бронирования переговорной комнаты.  
                2. Комната предоставляется пользователю строго в указанное время.  
                3. Пользователь обязуется соблюдать правила пользования комнатой и возместить ущерб в случае его нанесения.  

                **Контактная информация:**  
                Для вопросов и уточнений свяжитесь с администрацией:  
                Email: inkviz05@mail.com  
                Телефон: +7 (983) 172-93-64  

                Спасибо за использование нашей системы!  
                """

        reservation = Reservation(
            room_id=room_id,
            user_id=user_id,
            start_date=start_date,
            start_time=start_time,
            duration=duration,
            contract=contract_text
        )
        db.session.add(reservation)
        db.session.commit()

        flash('Бронирование успешно! Нажмите кнопку "Скачать договор" для получения документа.', 'success')
        session['last_reservation_id'] = reservation.id
        return redirect(url_for('main'))

    rooms = Room.query.all()
    return render_template('main.html', rooms=rooms)


@app.route('/download_contract')
def download_contract():
    if 'user_id' not in session or 'last_reservation_id' not in session:
        return redirect(url_for('login'))

    reservation = Reservation.query.get(session['last_reservation_id'])
    if not reservation:
        flash('Договор не найден', 'error')
        return redirect(url_for('main'))

    return send_file(
        io.BytesIO(reservation.contract.encode()),
        as_attachment=True,
        download_name='booking_contract.txt',
        mimetype='text/plain'
    )


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('last_reservation_id', None)
    return redirect(url_for('login'))


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    reservations = Reservation.query.filter_by(user_id=user.id).all()
    return render_template('profile.html', user=user, reservations=reservations)


@app.route('/admin')
def admin_panel():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user.is_admin:
        flash('У вас нет доступа к этой странице', 'danger')
        return redirect(url_for('main'))
    rooms = Room.query.all()
    files = File.query.all()
    return render_template('admin.html', rooms=rooms, files=files)


@app.route('/admin/add_room', methods=['POST'])
def add_room():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user.is_admin:
        flash('У вас нет доступа к этой функции', 'danger')
        return redirect(url_for('main'))

    name = request.form['name']
    capacity = request.form['capacity']
    new_room = Room(name=name, capacity=capacity)
    db.session.add(new_room)
    db.session.commit()
    flash('Комната успешно добавлена', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/delete_room/<int:room_id>', methods=['GET', 'POST'])
def delete_room(room_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user.is_admin:
        flash('У вас нет доступа к этой функции', 'danger')
        return redirect(url_for('main'))

    room = Room.query.get(room_id)
    if room:
        if request.method == 'POST':
            for reservation in room.reservations:
                db.session.delete(reservation)
            db.session.delete(room)
            db.session.commit()
            flash('Комната и все связанные бронирования успешно удалены', 'success')
            return redirect(url_for('admin_panel'))
        else:
            return render_template('confirm_delete.html', room=room)
    else:
        flash('Комната не найдена', 'danger')
    return redirect(url_for('admin_panel'))


@app.route('/admin/upload_rooms', methods=['POST'])
def upload_rooms():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user.is_admin:
        flash('У вас нет доступа к этой функции', 'danger')
        return redirect(url_for('main'))

    if 'file' not in request.files:
        flash('Файл не выбран', 'danger')
        return redirect(url_for('admin_panel'))

    file = request.files['file']
    if file.filename == '':
        flash('Файл не выбран', 'danger')
        return redirect(url_for('admin_panel'))

    if file and file.filename.endswith('.csv'):
        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.reader(stream)
            next(csv_reader)  # Skip header row
            for row in csv_reader:
                name, capacity = row
                new_room = Room(name=name, capacity=int(capacity))
                db.session.add(new_room)
            db.session.commit()
            flash('Комнаты успешно загружены', 'success')
        except Exception as e:
            flash(f'Ошибка при загрузке файла: {str(e)}', 'danger')
    else:
        flash('Пожалуйста, загрузите файл CSV', 'danger')

    return redirect(url_for('admin_panel'))


@app.route('/admin/upload_file', methods=['POST'])
def upload_file():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user.is_admin:
        flash('У вас нет доступа к этой функции', 'danger')
        return redirect(url_for('main'))

    if 'file' not in request.files:
        flash('Файл не выбран', 'danger')
        return redirect(url_for('admin_panel'))

    file = request.files['file']
    if file.filename == '':
        flash('Файл не выбран', 'danger')
        return redirect(url_for('admin_panel'))

    if file:
        filename = secure_filename(file.filename)
        file_data = file.read()
        new_file = File(name=filename, data=file_data, mimetype=file.mimetype)
        db.session.add(new_file)
        db.session.commit()
        flash('Файл успешно загружен', 'success')
    else:
        flash('Ошибка при загрузке файла', 'danger')

    return redirect(url_for('admin_panel'))


@app.route('/files')
def file_list():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    files = File.query.all()
    user = User.query.get(session['user_id'])
    return render_template('file_list.html', files=files, is_admin=user.is_admin)


def process_text_content(content):
    # Заменяем табуляцию и пробелы на неразрывные пробелы
    content = content.replace('\t', '&nbsp;&nbsp;&nbsp;&nbsp;')
    content = re.sub(r' {2,}', lambda m: '&nbsp;' * len(m.group()), content)

    # Обрабатываем выравнивание
    lines = content.split('\n')
    processed_lines = []
    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith('<') and stripped_line.endswith('>'):
            # Это может быть HTML-тег, оставляем как есть
            processed_lines.append(line)
        elif stripped_line.startswith('|') and stripped_line.endswith('|'):
            # Это может быть строка таблицы, обрабатываем отдельно
            cells = [cell.strip() for cell in stripped_line.split('|')[1:-1]]
            processed_cells = []
            for cell in cells:
                if cell.startswith(':') and cell.endswith(':'):
                    align = 'center'
                elif cell.endswith(':'):
                    align = 'right'
                else:
                    align = 'left'
                processed_cells.append(f'<td style="text-align: {align};">{cell.strip(":")}</td>')
            processed_lines.append(f'<tr>{"".join(processed_cells)}</tr>')
        else:
            # Определяем выравнивание
            left_spaces = len(line) - len(line.lstrip())
            right_spaces = len(line) - len(line.rstrip())

            if left_spaces > 0 and right_spaces > 0:
                align = 'center'
            elif right_spaces > left_spaces:
                align = 'right'
            else:
                align = 'left'

            processed_lines.append(f'<div style="text-align: {align};">{html.escape(stripped_line)}</div>')

    return '\n'.join(processed_lines)


@app.route('/view_file/<int:file_id>')
def view_file(file_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    file = File.query.get(file_id)
    if file:
        if file.mimetype.startswith('text/'):
            encoding = chardet.detect(file.data)['encoding']
            content = file.data.decode(encoding)
            if file.mimetype == 'text/markdown':
                content = markdown.markdown(content, extensions=['fenced_code', 'codehilite', 'tables', 'nl2br'])
            elif file.mimetype == 'text/html':
                soup = BeautifulSoup(content, 'html.parser')
                content = soup.prettify()
            elif file.mimetype == 'text/csv':
                csv_content = list(csv.reader(io.StringIO(content)))
                headers = csv_content[0] if csv_content else []
                table_html = '<table class="table table-bordered">'
                table_html += '<thead><tr>'
                for header in headers:
                    table_html += f'<th>{header}</th>'
                table_html += '</tr></thead><tbody>'
                for row in csv_content[1:]:
                    table_html += '<tr>'
                    for cell in row:
                        table_html += f'<td>{cell}</td>'
                    table_html += '</tr>'
                table_html += '</tbody></table>'
                content = table_html
            else:
                try:
                    lexer = get_lexer_for_filename(file.name)
                except pygments.util.ClassNotFound:
                    lexer = TextLexer()
                formatter = HtmlFormatter(linenos=True, cssclass="source")
                content = pygments.highlight(content, lexer, formatter)

            content = process_text_content(content)
            return render_template('view_file.html', file=file, content=content, is_formatted=True,
                                   pygments_css=HtmlFormatter().get_style_defs('.source'))
        elif file.mimetype.startswith('image/'):
            content = base64.b64encode(file.data).decode('utf-8')
            return render_template('view_file.html', file=file, content=content, is_image=True)
        elif file.mimetype == 'application/pdf':
            pdf_document = fitz.open(stream=file.data, filetype="pdf")
            images = []
            for page in pdf_document:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_data = pix.tobytes("png")
                img_base64 = base64.b64encode(img_data).decode('utf-8')
                images.append(img_base64)
            return render_template('view_file.html', file=file, images=images, is_pdf=True)
        elif file.mimetype in ['application/msword',
                               'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
            result = mammoth.convert_to_html(io.BytesIO(file.data))
            content = result.value
            # Обработка таблиц
            soup = BeautifulSoup(content, 'html.parser')
            tables = soup.find_all('table')
            for table in tables:
                table['class'] = 'table table-bordered'
            content = str(soup)
            content = process_text_content(content)
            return render_template('view_file.html', file=file, content=content, is_formatted=True)
        else:
            return render_template('view_file.html', file=file)
    flash('Файл не найден', 'danger')
    return redirect(url_for('file_list'))


@app.route('/download_file/<int:file_id>')
def download_file(file_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    file = File.query.get(file_id)
    if file:
        return send_file(
            io.BytesIO(file.data),
            as_attachment=True,
            download_name=file.name,
            mimetype=file.mimetype
        )
    flash('Файл не найден', 'danger')
    return redirect(url_for('file_list'))


@app.route('/admin/delete_file/<int:file_id>', methods=['POST'])
def delete_file(file_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user.is_admin:
        flash('У вас нет доступа к этой функции', 'danger')
        return redirect(url_for('main'))

    file = File.query.get(file_id)
    if file:
        db.session.delete(file)
        db.session.commit()
        flash('Файл успешно удален', 'success')
    else:
        flash('Файл не найден', 'danger')
    return redirect(url_for('admin_panel'))


if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists('rooms.db'):
            init_db()
    app.run(debug=True)

