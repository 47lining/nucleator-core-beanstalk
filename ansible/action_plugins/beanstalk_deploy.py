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

import ansible

from ansible.callbacks import vv
from ansible.errors import AnsibleError as ae
from ansible.runner.return_data import ReturnData
from ansible import utils
from ansible.utils import parse_kv, template
from ansible.inventory import Inventory
from ansible.inventory.host import Host
from ansible.inventory.group import Group

import boto.beanstalk
import boto.ec2
import boto.s3
from boto.s3.key import Key

import os
import os.path
import sys
import time

class ActionModule(object):
    """
    An action plugin to deploy to beanstalk from an accessible source url.
    """
    
    ### Make sure runs once per play only
    BYPASS_HOST_LOOP = True
    #TRANSFERS_FILES = False

    def __init__(self, runner):
        self.runner = runner

    def run(self, conn, tmp, module_name, module_args, inject, complex_args=None, **kwargs):
        try:
            args = {}
            if complex_args:
                args.update(complex_args)
            args.update(parse_kv(module_args))

            data = {}
            data.update(inject)

            # Get the region associated with the target cage
            region = args["region"]

            # Get an s3 connection
            s3conn = boto.s3.connect_to_region(region)
            
            # Get an elastic beanstalk connection
            ebsconn = boto.beanstalk.connect_to_region(region)

            # Get args and create a unique keyname for the application version
            env_name = args["environment_name"]
            app_name = args["application_name"]
            app_version = args["application_version"]
            app_url = args["application_url"]
            bucket_name = args["bucket_name"]
            key_prefix = args["key_prefix"]
            timestamp = str(int(time.time()))
            if app_url.find('.war') > -1:
                file_ext = ".war"
            elif app_url.find('.zip') > -1:
                file_ext = ".zip"
            else:
                file_ext = ""
                print "Could not determine artifact format from url - not injecting nucleator config!"
            keyname = app_name + "-" + app_version + "-" + timestamp + file_ext

            # See if this is the first deploy to happen after initial beanstalk setup (true
            # if there is only the initial application version). If so we are going to want
            # to kill all EC2 instances after deploy so their replacements pick up tags.
            result = ebsconn.describe_application_versions(application_name=app_name)
            versions = result["DescribeApplicationVersionsResponse"]["DescribeApplicationVersionsResult"]["ApplicationVersions"]
            first_deploy = len(versions) == 1

            # Local temp filename to download the source artifact to   
            filename = os.path.join("/tmp", keyname)
            
            # Download the artifact from app_url to temp file
            os.system("curl --insecure %s > %s" % (app_url, filename))

            # Inject nucleator.config into the deployment artifact
            config_file = args["config_file"]

            print "Injecting nucleator config %s into %s" % (config_file, filename)
            current_dir = os.getcwd()
            if os.path.exists("/tmp/.ebextensions"):
                os.system("rm -rf /tmp/.ebextensions")
            os.mkdir("/tmp/.ebextensions")
            os.system("cp %s /tmp/.ebextensions/" % config_file)
            os.chdir("/tmp")
            config_file_name = os.path.split(config_file)[-1]
            archive_file_name = os.path.split(filename)[-1]

            if app_url.find('.war') > -1:
                os.system("jar uf %s .ebextensions/%s" % (archive_file_name, config_file_name))
            elif app_url.find('.zip') > -1:
                os.system("zip -u %s .ebextensions/%s" % (archive_file_name, config_file_name))

            os.chdir(current_dir)

            # Upload the artifact to s3
            bucket = s3conn.get_bucket(bucket_name)
            
            s3key = '/'.join([key_prefix, keyname])
            
            k = Key(bucket)
            k.key = s3key
            k.set_metadata('time', timestamp)
            k.set_contents_from_filename(filename)

            # Give s3 some time to get consistent
            time.sleep(30)

            # This script may be invoked directly after provisioning, in which case we may need
            # to wait for the instance to be totally back up before redeploying.
            self.wait_for_health(region, app_name, "Green")


            # Create new application version
            ebsconn.create_application_version(app_name, app_version, s3_bucket=bucket_name, s3_key=s3key)
            
            # Cause the new version to be deployed
            ebsconn.update_environment(environment_name=env_name, version_label=app_version)
            
            # Wait for Grey to indicate update has started, then Green to ensure it has completed
            self.wait_for_health(region, app_name, "Grey")
            self.wait_for_health(region, app_name, "Green")
            
            time.sleep(30)
            
            if first_deploy:
                # Find and terminate all EC2 instances related to the beanstalk so that they will 
                # pick up tagging information included in the injected nucleator.config file
                print "Terminating current ec2 instances so that their replacements pick up tags"

                ec2conn = boto.ec2.connect_to_region(region)

                result = ebsconn.describe_environment_resources(environment_name=env_name)
                
                instlist = result["DescribeEnvironmentResourcesResponse"]["DescribeEnvironmentResourcesResult"]["EnvironmentResources"]["Instances"]
                idlist = []
                for item in instlist:
                    idlist.append(item["Id"])

                ec2conn.terminate_instances(instance_ids=idlist)


                # Wait for beanstalk health to turn Red which indicates all of the ec2 instances are gone
                self.wait_for_health(region, app_name, "Red")

                # Wait for beanstalk health to turn Green which indicates all of the instances are back
                self.wait_for_health(region, app_name, "Green")

        except Exception, e:
            result = dict(failed=True, msg=type(e).__name__ + ": " + str(e))
            return ReturnData(conn=conn, comm_ok=False, result=result)

        result = dict(failed=False, changed=True)
        
        return ReturnData(conn=conn, comm_ok=True, result=result)

    def wait_for_health(self, region, app_name, health, timeout=900):
        VALID_BEANSTALK_HEALTHS = ('Green', 'Yellow', 'Red', 'Grey')
            
        if not health in VALID_BEANSTALK_HEALTHS:
            raise ValueError(health + " is not a valid beanstalk health value")

        timeout_time = time.time() + timeout
        
        ebsconn = boto.beanstalk.connect_to_region(region)

        while 1:
            print "Waiting for beanstalk %s to turn %s" % (app_name, health)
                
            result = ebsconn.describe_environments(application_name=app_name)
            current_health = result["DescribeEnvironmentsResponse"]["DescribeEnvironmentsResult"]["Environments"][0]["Health"]
            print "Current health is: %s" % current_health

            if current_health == health:
                print "Beanstalk %s has turned %s" % (app_name, health)
                break
                
            if time.time() > timeout_time:
                raise ValueError("The timeout has expired")
                
            time.sleep(15)
