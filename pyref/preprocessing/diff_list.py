import json
from os import path
import threading
from pyref.preprocessing.revision import Rev
import os
import time
import signal
from pyref.preprocessing.utils import to_tree

import pandas as pd
from ast import  *

import logging


class RepeatedTimer(object):
    # from https://stackoverflow.com/a/40965385
    def __init__(self, interval, function, *args, **kwargs):
        self._timer = None
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.next_call = time.time()
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

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
    logging.warn("Commit skipped due to the long processing time")
    raise TimeoutError


def execution_reminder():
    logging.info("Please wait, the process is still running. ", time.ctime())


def _handle_single_commit(changes_path, commit_id_str, refactorings, directory=None, skip_time=None):
    commit_file_path = f'{changes_path}{os.sep}{commit_id_str}.csv'
    df = pd.read_csv(commit_file_path)
    if directory is not None:
        df = df[df["Path"].isin(directory)]

    rev_a = Rev()
    rev_b = Rev()
    df.apply(lambda row: populate(row, rev_a, rev_b), axis=1)

    if skip_time is not None:
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(int(float(skip_time) * 60))
    rt = RepeatedTimer(480, execution_reminder)
    try:
        rev_difference = rev_a.revision_difference(rev_b)
        refs = rev_difference.get_refactorings()
        for refactoring in refs:
            refactorings.append((refactoring, commit_id_str))
            logging.debug("Found refactoring [%s]", str(refactoring))

    except Exception as e:
        logging.warn("Failed to process commit.", e)
    except TimeoutError as e:
        logging.warn("Commit skipped due to the long processing time")
    finally:
        rt.stop()
        if skip_time is not None:
            signal.alarm(0)


def build_diff_lists(changes_path, commit=None, directory=None, skip_time=None):
    refactorings = list()

    if commit is not None:
        _handle_single_commit(changes_path, commit, refactorings, directory, skip_time)
    else:
        for root, dirs, files in os.walk(changes_path):
            for _, commit_file_name in enumerate(files):
                if commit_file_name.endswith(".csv"):
                    commit_id_str = commit_file_name.split(".")[0]
                    _handle_single_commit(changes_path, commit_id_str, refactorings, directory)

    output_refactorings_to_json(changes_path, refactorings)

    return refactorings


def output_refactorings_to_json(changes_path, refactorings):
    refactorings.sort(key=lambda x: x[1])
    json_outputs = list()
    for refactoring in refactorings:
        logging.info("commit=[%3s]; refactoring=[%s]", refactoring[1], str(refactoring[0]).strip())
        data = refactoring[0].to_json_format()
        data["Commit"] = refactoring[1]
        json_outputs.append(data)
    json_path = f'{changes_path}{os.sep}refactorings.json'
    with open(json_path, 'w') as outfile:
        outfile.write(json.dumps(json_outputs, indent=4))


def extract_refs(args):
    # owner_name = args.repo.split("/")[0]
    # repo_name = args.repo.split("/")[1]

    from pyref.repomanager import repo_changes

    repo_path = args.repopath
    if args.skip is not None:
        skip_time = args.skip
        print("\nCommit will be skipped if the processing time is longer than", skip_time, 'minutes.')
    else:
        skip_time = None
    if args.commit is not None:
        repo_changes.all_commits(repo_path, [args.commit])
        print("\nExtracting Refs...")
        build_diff_lists(repo_path + "/changes/", args.commit, args.directory, skip_time)
    else:
        print("\nExtracting commit history...")
        repo_changes.all_commits(repo_path)
        print("\nExtracting Refs...")
        build_diff_lists(repo_path + "/changes/", args.directory, skip_time=skip_time)


def validate(args):
    validations = pd.read_csv(args.path)
    validations["correct"] = validations["correct"].apply(lambda x: 'true' if x == 1 else 'false')
    validations = validations.groupby(['commit']).agg(lambda x: ','.join(x)).reset_index()
    validations["project"] = validations["project"].apply(lambda x: x.split(",")[0])
    validations = validations.to_dict("records")

    from pyref.repomanager import repo_changes
    from pyref.repomanager import repo_utils

    for validation in validations:
        if validation["commit"] == "bf9c26bb128d50ff8369c3bc7fbfc63d066d1ea8" or not "false" in validation["correct"]:
            continue

        repo = validation["project"].split("_")
        print(
            "-----------------------------------------------------------------------------------------------------------")
        print("Cloning %s/%s" % (repo[0], repo[1]))
        repo_utils.clone_repo(repo[0], repo[1])

        while not path.exists("./Repos/" + repo[1]):
            time.sleep(1)

        path_to_repo = "./Repos/" + repo[1]
        repo_changes.all_commits(path_to_repo, [validation["commit"]])

        while not path.exists("./Repos/" + repo[1] + "/changes/" + validation["commit"] + ".csv"):
            time.sleep(1)

        print("Validation of %s: %s" % (validation["type"], validation["correct"]))

        changes_path = "./Repos/" + repo[1] + "/changes/"
        build_diff_lists(changes_path, validation["commit"])


def populate(row, rev_a, rev_b):
    path = row["Path"]
    rav_a_tree = to_tree(eval(row["oldFileContent"]))
    rev_b_tree = to_tree(eval(row["currentFileContent"]))
    rev_a.extract_code_elements(rav_a_tree, path)
    rev_b.extract_code_elements(rev_b_tree, path)


def build_diff_lists_args(args):
    build_diff_lists(args.path, args.commit)
