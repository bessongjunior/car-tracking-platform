from flask import jsonify


def success(data=None, message='Success', status=200):
    payload = {'status': 'success', 'message': message}
    if data is not None:
        payload['data'] = data
    return jsonify(payload), status


def error(message='An error occurred', status=400, errors=None):
    payload = {'status': 'error', 'message': message}
    if errors:
        payload['errors'] = errors
    return jsonify(payload), status
