import json
import time

import requests


class Client(object):
    """Phabricator client"""

    def __init__(self, url, username, key):
        self.url = url
        self.username = username
        self.column_cache = {}
        self.phid_cache = {}
        self.session = {
            'token': key,
        }

    @classmethod
    def newFromCreds(cls):
        with open('creds.json', 'r') as f:
            creds = json.loads(f.read())
        return cls(*creds)

    def post(self, path, data):
        data['__conduit__'] = self.session
        r = requests.post('%s/api/%s' % (self.url, path), data={
            'params': json.dumps(data),
            'output': 'json',
        })
        resp = r.json()
        if resp['error_code'] is not None:
            raise Exception(resp['error_info'])
        return resp['result']

    def lookupPhid(self, label):
        """Lookup information on a Phab object by name."""
        if not self.phid_cache.get(label):
            r = self.post('phid.lookup', {'names': [label]})
            if label in r and 'phid' in r[label]:
                obj = r[label]['phid']
                self.phid_cache[label] = obj
            else:
                raise Exception('No object found for %s' % label)
        return self.phid_cache[label]

    def getColumns(self, project_phid):
        if not self.column_cache.get(project_phid):
            self.column_cache[project_phid] = self.post(
                'project.column.search', {
                    "constraints": {
                        "projects": [project_phid]}})
        return self.column_cache[project_phid]

    def moveColumns(self, task_phid, to_column):
        self.post('maniphest.edit', {
            'objectIdentifier': task_phid,
            'transactions': [{
                'type': 'column',
                'value': [to_column],
            }]
        })

    def taskDetails(self, phid):
        """Lookup details of a Maniphest task."""
        r = self.post('maniphest.query', {'phids': [phid]})
        if phid in r:
            return r[phid]
        raise Exception('No task found for phid %s' % phid)

    def getTransactions(self, phid):
        r = self.post('transaction.search', {'objectIdentifier': phid})
        if 'data' in r:
            return r['data']
        raise Exception('No transaction found for phid %s' % phid)

    def removeProject(self, project_phid, task):
        return self.removeProjectByPhid(project_phid, self.lookupPhid(task))

    def removeProjectByPhid(self, project_phid, task_phid):
        self.post('maniphest.edit', {
            'objectIdentifier': task_phid,
            'transactions': [{
                'type': 'projects.remove',
                'value': [project_phid],
            }]
        })

    def getTasksWithProject(self, project_phid, continue_=None):
        r = self._getTasksWithProjectContinue(project_phid, continue_)
        cursor = r['cursor']
        for case in r['data']:
            if case['type'] != 'TASK':
                continue
            yield case['phid']
        if cursor.get('after'):
            for case in self.getTasksWithProject(
                    project_phid, cursor['after']):
                yield case

    def _getTasksWithProjectContinue(self, project_phid, continue_=None):
        params = {
            'limit': 100,
            'constraints': {
                'projects': [project_phid],
                "modifiedStart": int(time.time() - 3600)
            }
        }
        if continue_:
            params['after'] = continue_
        return self.post('maniphest.search', params)

    def getTaskColumns(self, phid):
        params = {
            "attachments": {
                "columns": {"boards": {"columns": True}}
            },
            "constraints": {
                "phids": [phid]
            }
        }
        return self.post('maniphest.search', params)[
            'data'][0]['attachments']['columns']
