# Copyright 2015 47Lining LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from nucleator.cli.utils import ValidateCustomerAction
from nucleator.cli.command import Command
from nucleator.cli import properties
from nucleator.cli import ansible

import os, subprocess, re, hashlib

class Beanstalk(Command):

    name = "beanstalk"

    # For a list of supported types see http://docs.aws.amazon.com/elasticbeanstalk/latest/dg/concepts.platforms.html
    # The URL to the sample app is best found by creating a new environment and then looking in the
    # CF template (ruby23_pass updated 3/21/17)
    beanstalk_types = {
        "java8": ("64bit Amazon Linux 2016.09 v2.4.4 running Java 8",
                 "AWS Elastic Beanstalk Environment running Java Sample Application",
                 "java-sample-app.zip"),
                # java-se-jetty-maven-v1.zip
        "java7": ("64bit Amazon Linux 2016.09 v2.4.4 running Java 7",
                  "AWS Elastic Beanstalk Environment running Java Sample Application",
                  "java-sample-app.zip"),
                # java-se-jetty-maven-v1.zip
        "nodejs":  ("64bit Amazon Linux 2016.03 v2.1.0 running Node.js",
                    "AWS Elastic Beanstalk Environment running NodeJs Sample Application",
                    "nodejs-sample.zip"),
        "python3": ("64bit Amazon Linux 2016.03 v2.1.3 running Python 3.4",
                    "AWS Elastic Beanstalk Environment running Python Sample Application",
                    "basicapp.zip"),
                    # "python-v1.zip"
        "python27" : ("64bit Amazon Linux 2016.03 v2.1.0 running Python 2.7",
                      "AWS Elastic Beanstalk Environment running Python Sample Application",
                      "basicapp.zip"),
                    # "python-v1.zip"
        "ruby23_pass": ("64bit Amazon Linux 2016.09 v2.3.2 running Ruby 2.3 (Passenger Standalone)",
                        "AWS Elastic Beanstalk Environment running Ruby Passenger Sample Application",
                        "ruby/passenger-sample-20160218.zip"),
        "ruby23_puma": ("64bit Amazon Linux 2016.03 v2.1.0 running Ruby 2.3 (Puma)",
                        "AWS Elastic Beanstalk Environment running Ruby Puma Sample Application",
                        "ruby-puma-v1.zip"),
        "ruby22_pass": ("64bit Amazon Linux 2016.03 v2.1.0 running Ruby 2.2 (Passenger Standalone)",
                        "AWS Elastic Beanstalk Environment running Ruby Passenger Sample Application",
                        "ruby-sample.zip"),
        "ruby22_puma": ("64bit Amazon Linux 2016.03 v2.1.0 running Ruby 2.2 (Puma)",
                        "AWS Elastic Beanstalk Environment running Ruby Puma Sample Application",
                        "ruby-sample.zip"),
        "tomcat8": ("64bit Amazon Linux 2016.09 v2.5.4 running Tomcat 8 Java 8",
                    "AWS Elastic Beanstalk Environment running Tomcat 8 Java 8",
                    "elasticbeanstalk-sampleapp.war"),
                    # "java-tomcat-v1.zip"
        "tomcat7": ("64bit Amazon Linux 2016.03 v2.1.0 running Tomcat 7 Java 7",
                    "AWS Elastic Beanstalk Environment running Tomcat 7 Java 7",
                    "elasticbeanstalk-sampleapp.war"),
                    # "java-tomcat-v1.zip"
        "tomcat7java6": ("64bit Amazon Linux 2016.03 v2.1.0 running Tomcat 7 Java 6",
                         "AWS Elastic Beanstalk Environment running Tomcat 7 Java 6",
                         "elasticbeanstalk-sampleapp.war"),
                    # "java-tomcat-v1.zip"
        "go": ("64bit Amazon Linux 2015.09 v2.0.7 running Go 1.4",
               "AWS Elastic Beanstalk Environment running Go 1.4",
               "golang-sample.zip"),
                # "go-v1.zip"
        "docker19": ("64bit Amazon Linux 2016.03 v2.1.0 running Docker 1.9.1",
                     "AWS Elastic Beanstalk Environment running Docker 1.9.1",
                     "docker-sample.zip"),
                     # "docker-singlecontainer-v1.zip"),
        "multidocker19": ("64bit Amazon Linux 2016.03 v2.1.0 running Multi-container Docker 1.9.1 (Generic)",
                     "AWS Elastic Beanstalk Environment running Multi-container Docker 1.9.1",
                     "docker-sample.zip")
                     # "docker-multicontainer-v2.zip"),
    }

    def parser_init(self, subparsers):
        """
        Initialize parsers for this command.
        """
        # add parser for builder command
        beanstalk_parser = subparsers.add_parser('beanstalk')
        beanstalk_subparsers=beanstalk_parser.add_subparsers(dest="subcommand")

        # provision subcommand
        beanstalk_provision=beanstalk_subparsers.add_parser('provision', help="provision a new nucleator beanstalk stackset")
        beanstalk_provision.add_argument("--customer", required=True, action=ValidateCustomerAction, help="Name of customer from nucleator config")
        beanstalk_provision.add_argument("--cage", required=True, help="Name of cage from nucleator config")
        beanstalk_provision.add_argument("--type", required=True, help="Type of beanstalk to provision (python or java)")
        beanstalk_provision.add_argument("--app-name", required=True, help="Name of beanstalk application to provision")
        beanstalk_provision.add_argument("--tier", required=False, help="Tier of beanstalk to provision (webserver or worker)")
        beanstalk_provision.add_argument("--beanstalk-instance-type", required=False, help="EC2 instance type to provision")
        beanstalk_provision.add_argument("--database-instance-type", required=False, help="Database instance type to provision (default: None)")
        beanstalk_provision.add_argument("--database-name", required=False, help="Name of database to provision")
        beanstalk_provision.add_argument("--database-user", required=False, help="Database username")
        beanstalk_provision.add_argument("--database-password", required=False, help="Database password")
        beanstalk_provision.add_argument("--minscale", required=False, help="Minimum size of autoscaling group (default 1)")
        beanstalk_provision.add_argument("--maxscale", required=False, help="Maximum size of autoscaling group (default 4)")
        beanstalk_provision.add_argument("--instance-service-role", required=False, help="Role to associate with instance profile assigned to beanstalk instances (default NucleatorBeanstalkServiceRunner)")
        beanstalk_provision.add_argument("--beanstalk-service-role", required=False, help="Role assumed by Elastic Beanstalk service to maintain and monitor environment (default NucleatorBeanstalkManager)")
        beanstalk_provision.add_argument("--queue-url", required=False, help="URL of the queue for the worker tier application to use instead of creating its own")
        beanstalk_provision.add_argument("--inactivity-timeout", required=False, help="Number of seconds for the inactivity timeout")
        beanstalk_provision.add_argument("--visibility-timeout", required=False, help="Number of seconds for the visibility timeout")

        # configure subcommand
        beanstalk_configure=beanstalk_subparsers.add_parser('configure', help="configure provisioned nucleator beanstalk stackset")
        beanstalk_configure.add_argument("--customer", required=True, action=ValidateCustomerAction, help="Name of customer from nucleator config")
        beanstalk_configure.add_argument("--cage", required=True, help="Name of cage from nucleator config")
        beanstalk_configure.add_argument("--app-name", required=False, help="Limit configuration to specified beanstalk name," +
                                                                            " configures all beanstalks if not specified")
        # deploy subcommand
        beanstalk_deploy=beanstalk_subparsers.add_parser('deploy', help="deploy to provisioned nucleator beanstalk stackset")
        beanstalk_deploy.add_argument("--customer", required=True, action=ValidateCustomerAction, help="Name of customer from nucleator config")
        beanstalk_deploy.add_argument("--cage", required=True, help="Name of beanstalk to deploy to")
        beanstalk_deploy.add_argument("--app-name", required=True, help="Name of the application to deploy")
        beanstalk_deploy.add_argument("--app-version", required=True, help="The version of the application to deploy")
        beanstalk_deploy.add_argument("--app-url", required=True, help="URL to the artifact to deploy")

        # delete subcommand
        beanstalk_delete=beanstalk_subparsers.add_parser('delete', help="delete specified nucleator beanstalk stackset")
        beanstalk_delete.add_argument("--customer", required=True, action=ValidateCustomerAction, help="Name of customer from nucleator config")
        beanstalk_delete.add_argument("--cage", required=True, help="Name of cage from nucleator config")
        beanstalk_delete.add_argument("--app-name", required=True, help="Name of beanstalk application")

    def provision(self, **kwargs):
        """
        This command provisions a new named Elastic Beanstalk instance in the indicated
        customer cage.
        """
        cli = Command.get_cli(kwargs)
        cage = kwargs.get("cage", None)
        customer = kwargs.get("customer", None)
        if cage is None or customer is None:
            raise ValueError("cage and customer must be specified")
        extra_vars={
            "cage_name": cage,
            "customer_name": customer,
            "verbosity": kwargs.get("verbosity", None),
            "debug_credentials": kwargs.get("debug_credentials", None),
        }

        bstype = kwargs.get("type", None)
        if not bstype in self.beanstalk_types.keys():
            raise ValueError("unsupported beanstalk type")


        kind, desc, sample_app = self.beanstalk_types[bstype]
        extra_vars["configuration_template_solution_stack_name"] = kind
        extra_vars["configuration_template_description"] = desc
        extra_vars["sample_keyname"] = sample_app

        basename = kwargs.get("app_name", None)
        if not basename:
            raise ValueError("invalid beanstalk name")
        namespaced_app_name="{0}-{1}-{2}".format(basename, cage, customer)
        namespaced_app_name = self.safe_hashed_name(namespaced_app_name, 100)
        extra_vars["cli_stackset_name"] = "beanstalk"
        extra_vars["cli_stackset_instance_name"] = namespaced_app_name
        extra_vars["application_name"] = basename
        extra_vars["namespaced_app_name"] = namespaced_app_name

        envname = "e-%s" % basename
        namespaced_envname="{0}-{1}-{2}".format(envname, cage, customer)
        namespaced_envname = self.safe_hashed_name(namespaced_envname, 23)
        extra_vars["environment_name"] = namespaced_envname

        self.validate_names(namespaced_app_name, namespaced_envname)

        for name in ("beanstalk_instance_type", "database_instance_type", "database_name", "database_user", "database_password"):
            value = kwargs.get(name, None)
            if value is not None:
                extra_vars[name] = value

        extra_vars["beanstalk_deleting"]=kwargs.get("beanstalk_deleting", False)

        extra_vars["inactivity_timeout"]=kwargs.get("inactivity_timeout")
        if extra_vars["inactivity_timeout"] is None:
            extra_vars["inactivity_timeout"] = 180
        extra_vars["visibility_timeout"]=kwargs.get("visibility_timeout")
        if extra_vars["visibility_timeout"] is None:
            extra_vars["visibility_timeout"] = 30

        print "inactivity_timeout = ", extra_vars["inactivity_timeout"]
        print "visibility_timeout = ", extra_vars["visibility_timeout"]

        extra_vars["instance_service_role"] = "NucleatorBeanstalkServiceRunner"
        if kwargs.get("instance_service_role", None) is not None:
            extra_vars["instance_service_role"] = kwargs.get("instance_service_role")

        extra_vars["beanstalk_service_role"] = "aws-elasticbeanstalk-service-role" #"NucleatorBeanstalkManager"
        if kwargs.get("beanstalk_service_role", None) is not None:
            extra_vars["beanstalk_service_role"] = kwargs.get("beanstalk_service_role")

        minscale = kwargs.get("minscale", None)
        if minscale is None:
            minscale = 1
        else:
            try:
                minscale = int(minscale)
            except ValueError:
                raise ValueError("minscale must be an integer")

        maxscale = kwargs.get("maxscale", None)
        if maxscale is None:
            maxscale = 4
        else:
            try:
                maxscale = int(maxscale)
            except ValueError:
                raise ValueError("maxscale must be an integer")

        tier = kwargs.get("tier", None)
        if tier is not None:
            if tier == 'worker' or tier == 'webserver':
                extra_vars["beanstalk_tiertype_arg"] = tier
            else:
                ValueError("tier must be 'worker' or 'webserver'")
        else:
            extra_vars["beanstalk_tiertype_arg"] = "webserver"

        queue_url = kwargs.get("queue_url", None)
        if queue_url is not None:
            if tier != 'worker':
                ValueError("queue_url is only used when tier is 'worker'")
            extra_vars["queue_url"] = queue_url

        if maxscale < minscale:
            raise ValueError("maxscale must be equal to or greater than minscale")

        extra_vars["beanstalk_autoscale_min_size"] = str(minscale)
        extra_vars["beanstalk_autoscale_max_size"] = str(maxscale)

        command_list = []
        command_list.append("account")
        command_list.append("cage")
        command_list.append("beanstalk")

        inventory_manager_rolename = "NucleatorBeanstalkProvisioner"

        playbook = "beanstalk_provision.yml"
        if extra_vars["beanstalk_deleting"]:
            playbook = "beanstalk_delete.yml"

        cli.obtain_credentials(commands = command_list, cage=cage, customer=customer, verbosity=kwargs.get("verbosity", None), debug_credentials=kwargs.get("debug_credentials", None))

        return cli.safe_playbook(self.get_command_playbook(playbook),
                                 inventory_manager_rolename,
                                 is_static=True, # dynamic inventory not required
                                 **extra_vars
        )

    def safe_hashed_name(self, value, max):
        length = len(value)
        if length < max:
            return value
        trunc = value[:max - 6]
        hashed = hashlib.md5(value).hexdigest()
        return trunc + hashed[:6]

    def validate_names(self, bsname, envname):
        alphanum = re.compile("^[a-zA-Z0-9-]*$")
        if len(bsname) > 99 or bsname.find('/') > -1:
            raise ValueError("Invalid namespaced application name {0} (must be < 100 characters and not contain a / character)".format(bsname))
        if alphanum.match(bsname) is None:
            raise ValueError("Invalid namespaced application name {0} (must contain only alphanumeric characters and dashes)".format(bsname))
        if len(envname) < 4 or len(envname) > 23 or envname.find('/') > -1:
            raise ValueError("Invalid namespaced beanstalk environment name {0} (must be < 23 characters and not contain a / character)".format(envname))
        if alphanum.match(envname) is None:
            raise ValueError("Invalid namespaced environment name {0} (must contain only alphanumeric characters and dashes)".format(envname))

    def configure(self, **kwargs):
        """
        This command configures a named Elastic Beanstalk instance that has been provisioned
        in the indicated customer cage.
        """
        cli = Command.get_cli(kwargs)
        cage = kwargs.get("cage", None)
        customer = kwargs.get("customer", None)
        if cage is None or customer is None:
            raise ValueError("cage and customer must be specified")
        extra_vars={
            "cage_name": cage,
            "customer_name": customer,
            "verbosity": kwargs.get("verbosity", None),
            "debug_credentials": kwargs.get("debug_credentials", None),
        }
        basename = kwargs.get("app_name", None)
        if basename:
            namespaced_app_name="{0}-{1}-{2}".format(basename, cage, customer)
            namespaced_app_name = self.safe_hashed_name(namespaced_app_name, 100)
            extra_vars["cli_stackset_name"] = "beanstalk"
            extra_vars["cli_stackset_instance_name"] = namespaced_app_name
            extra_vars["application_name"] = basename

        command_list = []
        command_list.append("beanstalk")

        inventory_manager_rolename = "NucleatorBeanstalkInventoryManager"

        cli.obtain_credentials(commands = command_list, cage=cage, customer=customer, verbosity=kwargs.get("verbosity", None), debug_credentials=kwargs.get("debug_credentials", None)) # pushes credentials into environment

        return cli.safe_playbook(
            self.get_command_playbook("beanstalk_configure.yml"),
            inventory_manager_rolename,
            **extra_vars
        )

    def deploy(self, **kwargs):
        """
        This command deploys a particular revision of an application to a provisioned
        Elastic Beanstalk instance running in the indicated customer cage.
        """
        cli = Command.get_cli(kwargs)
        cage = kwargs.get("cage", None)
        customer = kwargs.get("customer", None)
        if cage is None or customer is None:
            raise ValueError("cage and customer must be specified")
        extra_vars={
            "cage_name": cage,
            "customer_name": customer,
            "verbosity": kwargs.get("verbosity", None),
            "debug_credentials": kwargs.get("debug_credentials", None),
        }

        for name in ("app_name", "app_version"):
            if not kwargs.get(name, None):
                raise ValueError("%s must be specified" % name)

        basename=kwargs.get("app_name")
        namespaced_app_name="{0}-{1}-{2}".format(basename, cage, customer)
        namespaced_app_name = self.safe_hashed_name(namespaced_app_name, 100)
        extra_vars["cli_stackset_name"] = "beanstalk"
        extra_vars["cli_stackset_instance_name"] = namespaced_app_name
        extra_vars["application_name"] = basename
        extra_vars["namespaced_app_name"] = namespaced_app_name
        extra_vars["application_version"] = kwargs.get("app_version")
        extra_vars["application_url"] = kwargs.get("app_url")

        envname = "e-%s" % basename
        namespaced_envname = "{0}-{1}-{2}".format(envname, cage, customer)
        namespaced_envname = self.safe_hashed_name(namespaced_envname, 23)
        extra_vars["environment_name"] = namespaced_envname

        command_list = []
        command_list.append("account")
        command_list.append("beanstalk")

        inventory_manager_rolename = "NucleatorBeanstalkDeployer"

        cli.obtain_credentials(commands = command_list, cage=cage, customer=customer, verbosity=kwargs.get("verbosity", None), debug_credentials=kwargs.get("debug_credentials", None)) # pushes credentials into environment

        return cli.safe_playbook(
            self.get_command_playbook("beanstalk_deploy.yml"),
            inventory_manager_rolename,
            **extra_vars
        )

    def delete(self, **kwargs):
        """
        This command deletes the specified, previously provisioned Elastic Beanstalk instance from the indicated
        customer cage.
        """
        kwargs["beanstalk_deleting"]=True
        kwargs["type"]="java7" # type must be specified to leverage provision, although its value is a don't care
        return self.provision(**kwargs)

# Create the singleton for auto-discovery
command = Beanstalk()
