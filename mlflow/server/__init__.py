import os
import shlex

from flask import Flask, send_from_directory

from mlflow.server import handlers
from mlflow.server.handlers import get_artifact_handler
from gunicorn.app.base import BaseApplication
from gunicorn.six import iteritems


class MlFlowTrackingGunicornApplication(BaseApplication):
    def __init__(self, application, options=None):
        self.options = options or {}
        self.application = application
        super(MlFlowTrackingGunicornApplication, self).__init__()

    def load_config(self):
        config = dict([(key, value) for key, value in iteritems(self.options)
                       if key in self.cfg.settings and value is not None])
        for key, value in iteritems(config):
            self.cfg.set(key.lower(), value)

    # def init(self, parser, opts, args):
    #     return self.cfg

    def load(self):
        return self.application


# NB: These are internal environment variables used for communication between
# the cli and the forked gunicorn processes.
BACKEND_STORE_URI_ENV_VAR = "_MLFLOW_SERVER_FILE_STORE"
ARTIFACT_ROOT_ENV_VAR = "_MLFLOW_SERVER_ARTIFACT_ROOT"
STATIC_PREFIX_ENV_VAR = "_MLFLOW_STATIC_PREFIX"

REL_STATIC_DIR = "js/build"

app = Flask(__name__, static_folder=REL_STATIC_DIR)
STATIC_DIR = os.path.join(app.root_path, REL_STATIC_DIR)

for http_path, handler, methods in handlers.get_endpoints():
    app.add_url_rule(http_path, handler.__name__, handler, methods=methods)


def _add_static_prefix(route):
    prefix = os.environ.get(STATIC_PREFIX_ENV_VAR)
    if prefix:
        return prefix + route
    return route


# Serve the "get-artifact" route.
@app.route(_add_static_prefix('/get-artifact'))
def serve_artifacts():
    return get_artifact_handler()


# We expect the react app to be built assuming it is hosted at /static-files, so that requests for
# CSS/JS resources will be made to e.g. /static-files/main.css and we can handle them here.
@app.route(_add_static_prefix('/static-files/<path:path>'))
def serve_static_file(path):
    return send_from_directory(STATIC_DIR, path)


# Serve the index.html for the React App for all other routes.
@app.route(_add_static_prefix('/'))
def serve():
    return send_from_directory(STATIC_DIR, 'index.html')


def _run_server(file_store_path, default_artifact_root, host, port, workers, static_prefix,
                gunicorn_opts):
    """
    Run the MLflow server, wrapping it in gunicorn
    :param static_prefix: If set, the index.html asset will be served from the path static_prefix.
                          If left None, the index.html asset will be served from the root path.
    :return: None
    """
    env_map = {}
    if file_store_path:
        env_map[BACKEND_STORE_URI_ENV_VAR] = file_store_path
    if default_artifact_root:
        env_map[ARTIFACT_ROOT_ENV_VAR] = default_artifact_root
    if static_prefix:
        env_map[STATIC_PREFIX_ENV_VAR] = static_prefix

    bind_address = "%s:%s" % (host, port)
    opts = shlex.split(gunicorn_opts) if gunicorn_opts else []

    options = {
        'bind': bind_address,
        'workers': workers,
    }

    # options.update(env_map)
    os.environ.update(env_map)
    try:
        application = MlFlowTrackingGunicornApplication(app, options=options)
        application.run()
    except Exception as e:
        # TODO: Log this error or do something useful with it.
        raise e


if __name__ == "__main__":
    # TODO: Get this from config
    DEFAULT_LOCAL_FILE_AND_ARTIFACT_PATH = "./mlruns"

    default_artifact_root = DEFAULT_LOCAL_FILE_AND_ARTIFACT_PATH

    # TODO: Get this from config
    backend_store_uri = "mysql://root:root@localhost:3306/mlflow_metrics?charset=utf8"

    # TODO: Get this from config
    _run_server(backend_store_uri, default_artifact_root, "127.0.0.1", 5001, 1, None, [])
