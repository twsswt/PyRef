import json
import logging
import os
import pathlib
import signal
import time
import threading

from os import path

import pandas as pd
from ast import *

import pandas.errors

from pyref.preprocessing.revision import Rev
from pyref.preprocessing.utils import to_tree


class RepeatedTimer(object):
    # from https://stackoverflow.com/a/40965385
    def __init__(self, interval):
        self._timer = None
        self.interval = interval
        self.is_running = False
        self.next_call = time.time()
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        logging.warning("Commit skipped due to the long processing time")

    def start(self):
        if not self.is_running:
            self.next_call += self.interval
            self._timer = threading.Timer(self.next_call - time.time(), self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False


def timeout_handler(num, stack):
    logging.warning("Commit skipped due to the long processing time")
    raise TimeoutError


def _get_refactorings_from_commit_diffs_file(commit_file_path, directory=None, skip_time=None):
    try:
        df = pd.read_csv(commit_file_path)
    except pandas.errors.EmptyDataError:
        return list()

    if directory is not None:
        df = df[df["Path"].isin(directory)]

    rev_a = Rev()
    rev_b = Rev()
    df.apply(lambda row: populate(row, rev_a, rev_b), axis=1)

    if skip_time is not None:
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(int(float(skip_time) * 60))
    rt = RepeatedTimer(480)
    try:
        rev_difference = rev_a.revision_difference(rev_b)
        return list(rev_difference.get_refactorings())

    except Exception as e:
        logging.warning(f'Failed to process commit file {commit_file_path}.', e)
    except TimeoutError as e:
        logging.warning(f'Commit file {commit_file_path} skipped due to the long processing time.')
    finally:
        rt.stop()
        if skip_time is not None:
            signal.alarm(0)


def _output_refactorings_to_json(commit_id_str, refactorings, project_refactorings_dir):
    logging.debug('Exporting commit=[%3s]; with [%n] refactorings.', commit_id_str, len(refactorings))
    json_root_object = {
        'commit': commit_id_str,
        'refactorings': [refactoring.to_json_format() for refactoring in refactorings]
    }

    with open(f'{project_refactorings_dir}{os.sep}{commit_id_str}', 'w') as outfile:
        outfile.write(json.dumps(json_root_object, indent=4))


def extract_refactorings_for_commit(
        commit_id_str,
        changes_path,
        directory=None,
        skip_time=None,
        project_refactorings_dir_name=None):

    commit_diffs_path = f'{changes_path}{os.sep}{commit_id_str}.csv'
    refactorings = _get_refactorings_from_commit_diffs_file(commit_diffs_path, directory, skip_time)

    if project_refactorings_dir_name is not None:
        _output_refactorings_to_json(commit_id_str, refactorings, project_refactorings_dir_name)

    return refactorings


def build_diff_lists(changes_path, directory=None, skip_time=None, project_refactorings_dir=None):

    pathlib.Path(project_refactorings_dir).mkdir(parents=True, exist_ok=True)

    refactorings = list()

    for root, dirs, files in os.walk(changes_path):
        for _, commit_file_name in enumerate(files):
            if commit_file_name.endswith(".csv"):
                commit_id_str = commit_file_name.split(".")[0]
                commit_refactorings = extract_refactorings_for_commit(
                    commit_id_str, changes_path, directory, skip_time, project_refactorings_dir)
                refactorings.append((commit_id_str, commit_refactorings))

    return refactorings


def populate(row, rev_a, rev_b):
    path = row["path"]
    rav_a_tree = to_tree(eval(row["oldFileContent"]))
    rev_b_tree = to_tree(eval(row["currentFileContent"]))
    rev_a.extract_code_elements(rav_a_tree, path)
    rev_b.extract_code_elements(rev_b_tree, path)
