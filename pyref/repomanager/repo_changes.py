import ast
import os
import pathlib

import pandas as pd
from git import Repo


def repository_commits(repo, specific_commits=None):
    result = list()

    for commit in repo.iter_commits():
        if specific_commits is None:
            result.append(commit)
        elif str(commit) in specific_commits:
            result.append(commit)

    return result


def _get_item_content_from_commit(commit, item, repo):
    return ast.dump(ast.parse(repo.git.show(f'{commit.hexsha}:{item.a_path}')), include_attributes=True)


def extract_commit_differences(repo, commit, changes_directory):

    modified_files = list()

    if len(commit.parents) > 0:

        for item in commit.diff(commit.parents[0]).iter_change_type('M'):
            path = item.a_path
            if path.endswith('.py'):
                try:
                    old_item_content = _get_item_content_from_commit(commit.parents[0], item, repo)
                    current_item_content = _get_item_content_from_commit(commit, item, repo)
                except Exception as _:
                    continue

                modified_files.append(
                    {'path': path,
                     'oldFileContent': old_item_content,
                     'currentFileContent': current_item_content
                     })

    data_frame = pd.DataFrame(modified_files)
    pathlib.Path(changes_directory).mkdir(parents=True, exist_ok=True)
    data_frame.to_csv(f'{changes_directory}{os.sep}/{str(commit)}.csv', index=False)
    return data_frame


def differences_from_commits(repo, specific_commits=None, changes_directory=None):

    _changes_directory = f'{repo.working_dir}{os.sep}changes' if not changes_directory else changes_directory

    result = list()

    commits = repository_commits(repo, specific_commits)

    for commit in commits:
        if len(commit.parents) == 1:
            commit_differences = extract_commit_differences(commit, repo, _changes_directory)
            result.append((commit, commit_differences))

    return result


def last_commit_changes(repo_path, changes_directory=None):
    repo = Repo(repo_path)
    commit = repo.head.commit

    _changes_directory = f'{repo.working_dir}{os.sep}changes' if not changes_directory else changes_directory

    if len(commit.parents) == 1:
        commit_differences = extract_commit_differences(repo, commit, changes_directory)
        commit_differences.to_csv(f'{_changes_directory}{os.sep}/{str(commit)}.csv', index=False)


def repo_changes_args(args):
    if args.lastcommit:
        last_commit_changes(args.path)
    if args.allcommits:
        differences_from_commits(args.path)
