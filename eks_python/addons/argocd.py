from aws_cdk import (Resource)
import aws_cdk.aws_eks as eks
from ..configuration.config import *
from jinja2 import Environment, FileSystemLoader
import os 
import yaml
import base64
from cdk_sops_secrets import SopsSecret

DIR = os.path.dirname(os.path.realpath(__file__))

class ArgocdApp(Resource):
    def __init__(self, scope, id , **kwargs):
        super().__init__(scope, id)
        
        privatekey = self.node.get_context('privatekey')
        if privatekey == None:
            raise Exception("you should provide the private key of your git repo")
        
        cluster = None 
        if 'cluster' in kwargs:
            cluster = kwargs['cluster']
        else:
            raise Exception("you should provide the cluster arg")
        
        dexconf = ''

        for key in dexapplications.keys():
            dexconf = dexconf + f"- type: {key}\n  id: {key}\n  name: {key.capitalize()}\n  config:\n    baseURL: {"https://gitlab.com" if key.lower() == 'gitlab' else 'https://github.com'}\n    clientID: {dexapplications[key]['clientid']}\n    clientSecret: {dexapplications[key]['clientsecret']}\n    redirectURI: http://argocd-dex-server:5556/dex/callback\n"
        
        argohelm = eks.HelmChart(self, "argocdchart",
                      cluster= cluster,
                      namespace= "argocd",
                      repository="https://argoproj.github.io/argo-helm",
                      release="argocd",
                      wait=False,
                      chart="argo-cd",
                      values= {
                          "global":{
                              "domain": argocd['hostname']
                          },
                          "server": {
                           "ingress":{
                               "enabled": "true",
                               "ingressClassName": "ingress-nginx",
                               "annotations": {
                                   "cert-manager.io/cluster-issuer": "dns-01-production",
                                   "nginx.ingress.kubernetes.io/backend-protocol": "HTTPS"
                               },
                               "tls": "true",
                               "hostname": argocd['hostname']
                            }
                          },
                          "configs":{
                              "cm":{
                                  "dex.config": "connectors:\n"+dexconf
                                }
                              }
                          }
                      
                    )
        
        env = Environment(loader=FileSystemLoader(DIR))
        template = env.get_template('argocd_project_app.yaml.j2')
        rendered_template = template.render({
                    "namespace": "argocd",
                    "type": base64.b64encode("git".encode('utf-8')).decode('utf-8'),
                    "repo_url": base64.b64encode(argocd['manifestrepo'].encode('utf-8')).decode('utf-8'),
                    "git_repo_url": argocd['manifestrepo'],
                    "privatekey": privatekey
                })
        
        documents = yaml.load_all(rendered_template)
        for index, manifest in enumerate(documents):
            resource = cluster.add_manifest(manifest['kind'], manifest)
            resource.node.add_dependency(argohelm)

        
        