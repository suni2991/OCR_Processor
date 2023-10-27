from flask import Flask, request,render_template,url_for, send_file, redirect,session
from flask_sqlalchemy import SQLAlchemy
import bcrypt
import os
import time
import uuid
import zipfile
import re
from utility import create_zip_file, is_pdf_by_extension, delete_files, num_page_check, split_pdf, combine_excels
from google_utility import quickstart, process_pdf


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)
app.secret_key = 'secret_key'

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(100))
    parser = db.Column(db.String(100))
    def __init__(self,username,password,parser):
        
        self.username = username
        self.password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        self.parser = parser
    def check_password(self,password):
        return bcrypt.checkpw(password.encode('utf-8'),self.password.encode('utf-8'))

with app.app_context():
    db.create_all()

# Contansts and Path Definition
excel_output_DIR = os.path.join(os.getcwd(), 'excel files')
pdf_output_DIR = os.path.join(os.getcwd(), 'split_pdfs')
output_DIR = os.path.join(os.getcwd(), 'output')
os.makedirs(excel_output_DIR, exist_ok=True)
os.makedirs(pdf_output_DIR, exist_ok=True)
os.makedirs(output_DIR, exist_ok=True)

# service account credentials
translate_service_key = 'service-account-key.json'
path_to_key = os.path.join(os.getcwd(), translate_service_key)

# Set the path to your service account key JSON file
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path_to_key

project_id = "mindful-rhythm-402207" 
location = "us"  # Format is "us" or "eu"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register',methods=['GET','POST'])
def register():
    if request.method == 'POST':
        # handle request
        
        username = request.form['username']
        password = request.form['password']
        parser = request.form['parser']
        new_user = User(username=username,password=password,parser=parser)
        db.session.add(new_user)
        db.session.commit()
        return redirect('/login')



    return render_template('register.html')

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        form_parser = user.parser
        if user and user.check_password(password):
            session['username'] = user.username
            return redirect('/dashboard')
        else:
            return render_template('login.html',error='Invalid user')

    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    if session['username']:
        user = User.query.filter_by(username=session['username']).first()
        return render_template('dashboard.html',user=user)
    
    return redirect('/login')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    if file:
        filename = file.filename
        unique_filename = f"{str(uuid.uuid4())}_{filename}"
        
        file.save(unique_filename)
        # file.save(filename)
        
        file_path = unique_filename
        unique_filename = re.sub('.pdf|.PDF' , '', file_path.split('\\')[-1])
        
        if 'username' in session:
            # Retrieve the user's parser choice from the session
            user = User.query.filter_by(username=session['username']).first()
            form_parser = user.parser

         
        # check if the file is a pdf
        if is_pdf_by_extension(file_path):
            
            # check the whether the pdf has more than N pages
            if num_page_check(file_path, 10):
                
                # if it has more than N pages then split it after each 10 page
                split_pdf(file_path, 10)
                
                # get a list of all pdf files after split.
                pdf_files = os.listdir('split_pdfs')
                
                #for each pdf 
                for pdf in pdf_files:
                    
                    # get name of pdf file
                    pdf_name = re.sub('.pdf|.PDF' , '', pdf)
                    
                    # get google document containing extracted text using form parser
                    parse_start = time.time()
                    
                    document = quickstart(
                        project_id,
                        location,
                        os.path.join(pdf_output_DIR, pdf),
                        form_parser)
                    
                    parse_end = time.time()
                    print(f'total time for extracting text from tables by form parser: {parse_end - parse_start} s')
                    
                    # convert the content of google document into table, translate it and then save as an excel file.
                    process_pdf(document, pdf_name)
                    
                # get name of all excel files
                excel_files = os.listdir(excel_output_DIR)
                print(excel_files)
                excel_files = [os.path.join(excel_output_DIR, file) for file in excel_files]
                    
                # combine these excel files (sheet-wise)
                combine_excels(excel_files, unique_filename)
                    
                    
                # once excel files are combined delete the parts of pdf file and excel files
                delete_files(pdf_output_DIR)
                delete_files(excel_output_DIR)
                
                output_file = os.path.join( output_DIR,  f'{unique_filename}_combined.xlsx' )  
                    
            else:
                
                # get name of pdf file
                pdf_name = re.sub('.pdf|.PDF' , '', file_path)
                    
                # get google document containing extracted text using form parser
                parse_start = time.time()
                    
                document = quickstart(
                        project_id,
                        location,
                        file_path,
                        form_parser)
                    
                parse_end = time.time()

                print(f'total time for extracting text from tables by form parser: {parse_end - parse_start} s')
                    
                # convert the content of google document into table, translate it and then save as an excel file.
                process_pdf(document, pdf_name)

                # once output is generated delete the parts of pdf file and excel files        
                output_file = os.path.join( excel_output_DIR,  f'{unique_filename}.xlsx' )   

        return redirect(url_for('download', filename=output_file))
    
@app.route('/download/<filename>')
def download(filename):    
    return send_file(filename, as_attachment=True)


@app.route('/logout')
def logout():
    session.pop('username',None)
    return redirect('/login')

if __name__ == '__main__':
    app.run(debug=True)