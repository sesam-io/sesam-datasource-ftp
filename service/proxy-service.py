from flask import Flask, request, Response, abort, send_file
from functools import wraps
import json
import logging
import os
from io import StringIO, BytesIO
from ftplib import FTP

app = Flask(__name__)

class FTPClient():
    """docstring for FTP"""
    def __init__(self, user, pwd, ftp_url):
        logger.debug("ftp connecting to {} with {}:{}".format(ftp_url, user, pwd))
        try:
            self.ftp = FTP(ftp_url)
            self.ftp.login(user, pwd)
        except Exception as e:
            raise e

    def get_stream(self, fpath):
        """return a file stream"""
        r = BytesIO()
        logger.debug("fetching {}".format(fpath))
        self.ftp.retrbinary('RETR {}'.format(fpath), r.write)
        return r

    def get_content(self, fpath):
        """return file as string"""
        resp = self.get_stream(fpath)
        return resp.getvalue()

def get_var(var):
    envvar = None
    if var.upper() in os.environ:
        envvar = os.environ[var.upper()]
    else:
        envvar = request.args.get(var)
    logger.info("Setting %s = %s" % (var, envvar))
    return envvar

def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth:
            return authenticate()
        return f(*args, **kwargs)

    return decorated

@app.route('/file', methods=['GET'])
@requires_auth
def get_file():
    logger.info("Get the request: {}".format(request.url))
    sys_id = request.args.get('sys')
    fpath = request.args.get('fpath')
    if not sys_id or not fpath:
        return abort(400, "Missing one of mandatory parameters.")
    auth = request.authorization
    sys_url = get_var(sys_id)
    if not sys_url:
        return abort(400, "Cannot find the endpoint url for {}".format(sys_id))
    f_stream = None
    if sys_url.startswith('ftp://'):
        logger.info("ftp url: {}".format(sys_url[6:]))
        try:
            client = FTPClient(auth.username, auth.password, sys_url[6:])
            f_stream = client.get_stream(fpath)
            f_stream.seek(0)
            return send_file(f_stream, attachment_filename="", as_attachment=True)
        except Exception as e:
            return abort(500, e)
        #f_c = client.get_content(fpath)
        #return Response(f_c)

if __name__ == '__main__':
    # Set up logging
    format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logger = logging.getLogger('http-ftp-proxy-microservice')

    # Log to stdout
    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(logging.Formatter(format_string))
    logger.addHandler(stdout_handler)

    logger.setLevel(logging.DEBUG)

    app.run(threaded=True, debug=True, host='0.0.0.0')
