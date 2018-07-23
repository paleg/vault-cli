"""
Copyright 2018 PeopleDoc
Written by Yann Lachiver
           Joachim Jablon

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import os

import click
import yaml

from vault_cli import vault_python_api

# Ordered by increasing priority
CONFIG_FILES = [
    '/etc/vault.yml',
    '~/.vault.yml',
    './.vault.yml',
]

CONTEXT_SETTINGS = {'help_option_names': ['-h', '--help']}


@click.group(context_settings=CONTEXT_SETTINGS)
@click.pass_context
@click.option('--url', '-U', help='URL of the vault instance',
              default='https://localhost:8200')
@click.option('--verify/--no-verify', default=True,
              help='Verify HTTPS certificate')
@click.option('--certificate', '-c', type=click.File('rb'),
              help='The certificate to connect to vault')
@click.option('--token', '-t', help='The token to connect to Vault')
@click.option('--token-file', '-T', type=click.File('rb'),
              help='File which contains the token to connect to Vault')
@click.option('--username', '-u',
              help='The username used for userpass authentication')
@click.option('--password-file', '-w', type=click.File('rb'),
              help='Can read from stdin if "-" is used as parameter')
@click.option('--base-path', '-b', help='Base path for requests')
def cli(ctx, **kwargs):
    """
    Interact with a Vault. See subcommands for details.
    """
    try:
        ctx.obj = vault_python_api.VaultSession(**kwargs)
    except ValueError as exc:
        raise click.UsageError(str(exc))


def read_config_file(file_path):
    try:
        with open(os.path.expanduser(file_path), "r") as f:
            config = yaml.safe_load(f)
    except IOError:
        return {}
    config.pop("config", None)

    # Because we're modifying the dict during iteration, we need to
    # consolidate the keys into a list
    for key in list(config):
        config[key.replace("-", "_")] = config.pop(key)

    _open_file(config, "certificate")
    _open_file(config, "password_file")
    _open_file(config, "token_file")

    return config


def _open_file(config, key):
    """
    Replace file name with open file at the given key
    in the config dict
    """
    try:
        config[key] = open(os.path.expanduser(config[key]), "rb")
    except KeyError:
        pass


@click.command("list")
@click.argument('path', required=False, default='')
@click.pass_obj
def list_(session, path):
    """
    List all the secrets at the given path. Folders are listed too. If no path
    is given, list the objects at the root.
    """
    result = vault_python_api.list_secrets(
        session=session.session, url=session.full_url(path))
    click.echo(result)


@click.command(name='get-all')
@click.argument('path', required=False, nargs=-1)
@click.pass_obj
def get_all(session, path):
    """
    Return multiple secrets. Return a single yaml with all the secrets located
    at the given paths. Folders are recursively explored. Without a path,
    explores all the vault.
    """
    result = {}

    # Just renaming the variable
    paths = path

    if not paths:
        paths = [""]

    for path in paths:
        if vault_python_api.is_dir(session=session.session,
                                   url=session.full_url(),
                                   path=path):
            secret = vault_python_api.get_recursive_secrets(
                session=session.session,
                url=session.full_url(path=path))
        else:
            secret = vault_python_api.get_secret(
                session=session.session,
                url=session.full_url(path=path))

        result.update(nested_keys(path, secret))

    if result:
        click.echo(yaml.safe_dump(
            result,
            default_flow_style=False,
            explicit_start=True))


def nested_keys(path, value):
    """
    >>> nested_path('test', 'foo')
    {'test': 'foo'}

    >>> nested_path('test/bla', 'foo')
    {'test': {'bla': 'foo'}}
    """
    try:
        base, subpath = path.strip('/').split('/', 1)
    except ValueError:
        return {path: value}
    return {base: nested_keys(subpath, value)}


@click.command()
@click.pass_obj
@click.option('--text',
              is_flag=True,
              help=("--text implies --without-key. Returns the value in "
                    "plain text format instead of yaml."))
@click.argument('name')
def get(session, text, name):
    """
    Return a single secret value.
    """
    secret = vault_python_api.get_secret(session=session.session,
                                         url=session.full_url(name))
    if text:
        click.echo(secret)
        return

    click.echo(yaml.safe_dump(secret,
                         default_flow_style=False,
                         explicit_start=True))


@click.command("set")
@click.pass_obj
@click.option('--yaml', 'format_yaml', is_flag=True)
@click.argument('name')
@click.argument('value', nargs=-1)
def set_(session, format_yaml, name, value):
    """
    Set a single secret to the given value(s).
    """
    if len(value) == 1:
        value = value[0]

    if format_yaml:
        value = yaml.safe_load(value)

    vault_python_api.put_secret(session=session.session,
                                url=session.full_url(name),
                                data={'value': value})
    click.echo('Done')


@click.command()
@click.pass_obj
@click.argument('name')
def delete(session, name):
    """
    Deletes a single secret.
    """
    vault_python_api.delete_secret(session=session.session,
                                   url=session.full_url(name))
    click.echo('Done')


cli.add_command(get_all)
cli.add_command(get)
cli.add_command(set_)
cli.add_command(list_)
cli.add_command(delete)


def build_config_from_files():
    config = {}
    config_files = CONFIG_FILES

    for potential_file in config_files:
        config.update(read_config_file(potential_file))

    return config


def main():
    config = build_config_from_files()

    return cli(default_map=config)
