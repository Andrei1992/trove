# Copyright 2014 Rackspace Hosting
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


def initialize(extra_opts=None, pre_logging=None):
    # Initialize localization support (the underscore character).
    import gettext
    gettext.install('trove', unicode=1)

    # Apply whole eventlet.monkey_patch excluding 'thread' module.
    # Decision for 'thread' module patching will be made
    # after debug_utils is set up.
    import eventlet
    eventlet.monkey_patch(all=True, thread=False)

    # Import only the modules necessary to initialize logging and determine if
    # debug_utils are enabled.
    import sys
    from trove.common import cfg
    from trove.common import debug_utils
    from trove.openstack.common import log as logging

    conf = cfg.CONF
    if extra_opts:
        conf.register_cli_opts(extra_opts)

    cfg.parse_args(sys.argv)
    if pre_logging:
        pre_logging(conf)

    logging.setup(None)
    debug_utils.setup()

    # Patch 'thread' module if debug is disabled
    if not debug_utils.enabled():
        eventlet.monkey_patch(thread=True)

    # Initialize Trove database.
    from trove.db import get_db_api
    get_db_api().configure_db(conf)

    return conf  # May be used by other scripts


def with_initialize(main_function=None, **kwargs):
    """
    Decorates a script main function to make sure that dependency imports and
    initialization happens correctly.
    """
    def apply(main_function):
        def run():
            conf = initialize(**kwargs)
            return main_function(conf)

        return run

    if main_function:
        return apply(main_function)
    else:
        return apply
