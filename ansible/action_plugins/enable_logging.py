import json
import boto
import yaml
import os
import time

from boto import s3

from ansible.runner.return_data import ReturnData
from ansible.utils import parse_kv, template
from ansible import utils

class ActionModule(object):
    def __init__(self, runner):
        self.runner = runner

    def run(self, conn, tmp, module_name, module_args, inject, complex_args=None, **kwargs):
        
		try:
			
			args = {}
			if complex_args:
				args.update(complex_args)
			args.update(parse_kv(module_args))

			logging_bucket = args["log_bucket"]
			account_number = args["account_number"]
			region = args["region"]

			envdict={}
			if self.runner.environment:
				env=template.template(self.runner.basedir, self.runner.environment, inject, convert_bare=True)
				env = utils.safe_eval(env)
			
			s3_conn = s3.connect_to_region(region, aws_access_key_id=env.get("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=env.get("AWS_SECRET_ACCESS_KEY"),
                    security_token=env.get("AWS_SECURITY_TOKEN"))

			bucketName = "elasticbeanstalk-%s-%s" % (region, account_number)

			bucket1 = s3_conn.get_bucket(bucketName)
			bucket2 = s3_conn.get_bucket(logging_bucket)
			response = bucket1.enable_logging(bucket2, "ElasticBeanstalkBucket/")

			return ReturnData(conn=conn,
                comm_ok=True,
                result=dict(failed=False, changed=False, msg="Logging Enabled"))

		except Exception, e:
			# deal with failure gracefully
			result = dict(failed=True, msg=type(e).__name__ + ": " + str(e))
			return ReturnData(conn=conn, comm_ok=False, result=result)

