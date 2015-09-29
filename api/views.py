from django.shortcuts import render
from django.http import JsonResponse
import psutil, json, os
from django.views.decorators.http import require_http_methods
from django.views.generic import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import time

import threading

from models import generate_key

#Error msgs
BAD_JSON_RESPONSE = { 'result': 'error', 'message': 'Bad JSON payload' }
NO_CMD_RESPONSE = { 'result': 'error', 'message': 'No "cmd" parameter' }
NO_PID_RESPONSE = { 'result': 'error', 'message': 'No "pid" parameter' }
BAD_CMD_RESPONSE = { 'result': 'error', 'message': 'The CMD doesn\'t exists' }
NO_PRIORITY_RESPONSE = { 'result': 'error', 'message': 'No "priority" parameter' }
BAD_PS_PATCH_RESPONSE = { 'result': 'error', 'message': 'Bad Data' }
BAD_PATCH_PRIORITY_RESPONSE = { 'result': 'error', 'message': 'Bad Priority' }
NOT_ENOUGH_PERMISSION_RESPONSE = { 'result': 'error', 'message': 'No enough permission for changing nice to process' }
BAD_PID_RESPONSE = { 'result': 'error', 'message': 'The PID is invalid' }
NO_PROCESS_PID_RESPONSE = { 'result': 'error', 'message': 'There is no process with the given PID' }
KILL_CURRENT_RESPONSE = { 'result': 'error', 'message': 'Can not kill current process' }
KILL_PARENT_RESPONSE = { 'result': 'error', 'message': 'Can not kill parent of current process' }

class NoCSRFView(View):
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super(NoCSRFView, self).dispatch(*args, **kwargs)

class PsView(NoCSRFView):
    def get(self, request):
        processes = []

        for p in psutil.process_iter():
            processes.append(p.as_dict())

        return JsonResponse({'processes':processes, 'result': 'ok'})

    def post(self, request):
        try:
            data = received_json_data=json.loads(request.body)
        except Exception as e:
            return JsonResponse(BAD_JSON_RESPONSE, status=400)

        if 'cmd' not in data:
            return JsonResponse(NO_CMD_RESPONSE, status=400)

        cmd = [data['cmd']]

        if 'args' in data:
            cmd = cmd + data['args']

        outputKey = generate_key()
        outfile = open('output/' + outputKey + '.out','w')
        errfile = open('output/' + outputKey + '.err','w')
        try:
            p = psutil.Popen(cmd, stdout=outfile, stderr=errfile)
        except OSError as e:
            outfile.close()
            errfile.close()
            return JsonResponse(BAD_CMD_RESPONSE, status=400)
        else:
            t = threading.Thread(target=runCmd, args=(p, outfile, errfile))
            t.start()

            return JsonResponse({'result': 'ok', 'process': p.pid, 'output': outputKey })

    def delete(self, request):
        try:
            data = received_json_data=json.loads(request.body)
        except Exception as e:
            return JsonResponse(BAD_JSON_RESPONSE, status=400)

        if 'pid' not in data:
            return JsonResponse(NO_PID_RESPONSE, status=400)

        try:
            pid = int(data['pid'])
        except Exception as e:
            return JsonResponse(BAD_PID_RESPONSE, status=400)

        if not psutil.pid_exists(pid):
            return JsonResponse(NO_PROCESS_PID_RESPONSE, status=400)

        current = psutil.Process(os.getpid())

        if current.pid == pid:
            return JsonResponse(KILL_CURRENT_RESPONSE, status=400)

        is_parent = False

        while True:

            if current.ppid() == pid:
                is_parent = True
                break

            if current.ppid() == 0:
                break

            current = psutil.Process(current.ppid())

        if is_parent:
            return JsonResponse(KILL_PARENT_RESPONSE, status=400)

        process = psutil.Process(pid)
        process.kill()

        return JsonResponse({'result':'ok'})

    def patch(self, request):
        try:
            data = received_json_data=json.loads(request.body)
        except Exception as e:
            return JsonResponse(BAD_JSON_RESPONSE, status=400)

        if 'pid' not in data:
            return JsonResponse(NO_PID_RESPONSE, status=400)

        if 'priority' not in data:
            return JsonResponse(NO_PRIORITY_RESPONSE, status=400)

        try:
            pid = int(data['pid'])
            priority = int(data['priority'])
        except Exception as e:
            return JsonResponse(BAD_PS_PATCH_RESPONSE, status=400)

        if priority > 20 or priority < -20:
            return JsonResponse(BAD_PATCH_PRIORITY_RESPONSE, status=400)

        if not psutil.pid_exists(pid):
            msg = 'No process with pid :' + str(pid)
            return JsonResponse({ 'result': 'error', 'message': msg }, status=400)
        process = psutil.Process(pid)

        try:
            process.nice(priority)
        except psutil.AccessDenied as e:
            return JsonResponse(NOT_ENOUGH_PERMISSION_RESPONSE, status=400)

        return JsonResponse({'result': 'ok'})

class ProcessView(NoCSRFView):
    def get(self, request, process):

        try:
            pid = int(process)
        except Exception as e:
            return JsonResponse(BAD_PID_RESPONSE, status=400)

        if not psutil.pid_exists(pid):
            return JsonResponse(NO_PROCESS_PID_RESPONSE, status=400)

        current = psutil.Process(os.getpid())
        return JsonResponse({'process': current.as_dict(), 'result': 'ok'})

class UserView(NoCSRFView):
    def get(self, request):
        users = {}

        for p in psutil.process_iter():
            name = p.username()
            if name not in users:
                users[name] = {
                    'username': name,
                    'running': 1
                }
                continue

            users[name]['running'] += 1

        user_list = []

        for u in users:
            user_list.append(users[u])

        return JsonResponse({'users': user_list, 'result': 'ok'})

class UserTaskView(NoCSRFView):
    def get(self, request, user):
        processes = []

        for p in psutil.process_iter():
            if p.username() != user:
                continue
            processes.append(p.as_dict())

        return JsonResponse({'processes':processes, 'result': 'ok'})

class ProcessOutputView(View):
    def get(self, request, output):
        outfile = open('output/' + output + '.out', 'r')
        errfile = open('output/' + output + '.err', 'r')
        response = {
            'out': "".join(line.rstrip() for line in outfile),
            'err': "".join(line.rstrip() for line in errfile),
        }
        outfile.close()
        errfile.close()
        return JsonResponse(response)

def runCmd(p, outfile, errfile):
    #Kill after a while
    #p.communicate
    time.sleep(10)
    if not p.poll():
        p.kill()

    outfile.close()
    errfile.close()
