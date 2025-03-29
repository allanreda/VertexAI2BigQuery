from flask import Flask, render_template
from flask_session import Session
import logging
import sys

###############################################################################
############################# App Configuration ##################################
###############################################################################

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app.config['SECRET_KEY'] = 'your_secret_key' # Input secret key for session management
app.config['SESSION_TYPE'] = 'filesystem'  # Define the session type to use filesystem
app.config['SESSION_PERMANENT'] = False  # Optional: Whether the session is permanent
app.config['SESSION_USE_SIGNER'] = True  # Optional: Sign the session cookie for extra security

Session(app)  # Initialize the Flask-Session extension

# Index route
@app.route('/', methods=['GET', 'POST'])
def index():
    rendered_html = render_template('index.html')
    return rendered_html