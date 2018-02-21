from flask import Flask, request, Response, abort, send_file
from functools import wraps
import json
import logging
import os
from io import StringIO, BytesIO
from ftplib import FTP
from ftplib import FTP_TLS
import ssl

app = Flask(__name__)

class MyFTP_TLS(FTP_TLS):
    """Explicit FTPS, with shared TLS session"""
    def ntransfercmd(self, cmd, rest=None):
        conn, size = FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            session = self.sock.session
            if isinstance(self.sock, ssl.SSLSocket):
                session = self.sock.session
            conn = self.context.wrap_socket(conn,
                                            server_hostname=self.host,
                                            session=session)  # this is the fix
        return conn, size


class FTPClient():
    """FTP Client"""
    def __init__(self, user, pwd, ftp_url):
        logger.debug("ftp connecting to {} with {}:{}".format(ftp_url, user, pwd))
        try:
            self.client = FTP(ftp_url)
            self.client.login(user, pwd)
        except Exception as e:
            raise e

    def test(self):
        return self.client.retrlines('LIST')

    def get_stream(self, fpath):
        """return a file stream"""
        r = BytesIO()
        logger.debug("fetching {}".format(fpath))
        self.client.retrbinary('RETR {}'.format(fpath), r.write)
        return r

    def get_content(self, fpath):
        """return file as string"""
        resp = self.get_stream(fpath)
        return resp.getvalue()

    def quit(self):
        self.client.quit()


class FTPSClient(FTPClient):
    """FTPS Client"""
    def __init__(self, user, pwd, ftp_url):
        logger.debug("ftps connecting to {} with {}:{}".format(ftp_url, user, pwd))
        try:
            self.client = MyFTP_TLS(ftp_url)
            self.client.login(user, pwd)
            self.client.prot_p()
            self.client.set_pasv(True)
        except Exception as e:
            raise e


def get_var(var):
    envvar = None
    if var.upper() in os.environ:
        envvar = os.environ[var.upper()]
    else:
        envvar = request.args.get(var)
    logger.debug("Setting %s = %s" % (var, envvar))
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

@app.route('/<sys_id>/file', methods=['GET'])
@requires_auth
def get_file(sys_id):
    fpath = request.args.get('fpath')
    if not fpath:
        return abort(400, "Missing the mandatory parameter.")
    auth = request.authorization
    sys_url = get_var(sys_id)
    if not sys_url:
        return abort(400, "Cannot find the endpoint url for {}".format(sys_id))
    f_stream = None
    client = None
    try:
        if sys_url.startswith('ftp://'):
                client = FTPClient(auth.username, auth.password, sys_url[6:])
        elif sys_url.startswith('ftps://'):
                client = FTPSClient(auth.username, auth.password, sys_url[7:])
        else:
            return abort(400, "Not supported protocal.")
        f_stream = client.get_stream(fpath)
        f_stream.seek(0)
        f_name = fpath.split('/')[-1]
        client.quit()
        return send_file(f_stream, attachment_filename=f_name, as_attachment=True)
    except Exception as e:
        return abort(500, e)


if __name__ == '__main__':
    # Set up logging
    format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logger = logging.getLogger('http-ftp-proxy-microservice')

    # Log to stdout
    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(logging.Formatter(format_string))
    logger.addHandler(stdout_handler)

    loglevel = os.environ.get("LOGLEVEL", "INFO")
    if "INFO" == loglevel.upper():
        logger.setLevel(logging.INFO)
    elif "DEBUG" == loglevel.upper():
        logger.setLevel(logging.DEBUG)
    elif "WARN" == loglevel.upper():
        logger.setLevel(logging.WARN)
    elif "ERROR" == loglevel.upper():
        logger.setLevel(logging.ERROR)
    else:
        logger.setlevel(logging.INFO)
        logger.info("Define an unsupported loglevel. Using the default level: INFO.")

    app.run(threaded=True, debug=True, host='0.0.0.0')
