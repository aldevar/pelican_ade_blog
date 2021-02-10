.. code-block:: python
  :linenos:
    
    import vyos.configtree
    import requests
    from requests.auth import HTTPBasicAuth

    # Set variables for edg_id and nsxmanager
    edge_id = 'edge-XXX'
    nsx_manager = 'nsxmanager.localdomain'

    def get_nat_dest_rule(config, path):
        '''
        From VyOS config section "nat destination rule X"
        Return the DNAT rule X as dict
        '''
        rule = dict()
        if config.exists(path + ["destination", "address"]):
            rule["dstaddr"] = config.return_value(path + ["destination", "address"])
        if config.exists(path + ["source", "address"]):
            rule["srcaddr"] = config.return_value(path + ["source", "address"])
        if config.exists(path + ["inbound-interface"]):
            rule["inbound-interface"] = config.return_value(path + ["inbound-interface"])
        if config.exists(path + ["log"]):
            rule["log"] = config.return_value(path + ["log"])
        if config.exists(path + ["protocol"]):
            rule["protocol"] = config.return_value(path + ["protocol"])
        if config.exists(path + ["description"]):
            rule["description"] = config.return_value(path + ["description"])
        if config.exists(path + ["translation", "address"]):
            rule["translateaddr"] = config.return_value(path + ["translation", "address"])

        return rule

    def get_nat_source_rule(config, path):
        '''
        From VyOS config section "nat source rule X"
        Return the SNAT rule X as dict
        '''
        rule = dict()
        if config.exists(path + ["source", "address"]):
            rule["srcaddr"] = config.return_value(path + ["source", "address"])
        if config.exists(path + ["destination", "address"]):
            rule["dstaddr"] = config.return_value(path + ["destination", "address"])
        if config.exists(path + ["outbound-interface"]):
            rule["outbound-interface"] = config.return_value(path + ["outbound-interface"])
        if config.exists(path + ["log"]):
            rule["log"] = config.return_value(path + ["log"])
        if config.exists(path + ["protocol"]):
            rule["protocol"] = config.return_value(path + ["protocol"])
        if config.exists(path + ["translation", "address"]):
            rule["translateaddr"] = config.return_value(path + ["translation", "address"])

        return rule

    def create_dstnat_payload(natdst):
        '''
        From all VyOS DNAT rules, create a XML payload that can be sent to NSX
        '''
        start_payload = "<natRules>"
        end_payload = "</natRules>"
        mid_payload = ""
        for rule in natdst.values():
            base_payload = "<natRule><action>dnat</action>\
                            <originalAddress>{0}</originalAddress>\
                            <translatedAddress>{1}</translatedAddress>\
                            <loggingEnabled>false</loggingEnabled>\
                            <enabled>true</enabled>\
                            <originalPort>any</originalPort>\
                            <translatedPort>any</translatedPort>".format(rule['dstaddr'], rule['translateaddr'])
            if "description" in rule:
                descr_payload = "<description>{0}</description>".format(rule['description'])
                base_payload = base_payload + descr_payload
            if "protocol" in rule:
                if rule['protocol'] == "all":
                    proto_payload = "<protocol>any</protocol>"
                else:
                    proto_payload = "<protocol>{0}</protocol>".format(rule['protocol'])
                
            else:
                proto_payload = "<protocol>any</protocol>"
            base_payload = base_payload + proto_payload
            if "srcaddr" in rule:
                src_payload = "<dnatMatchSourceAddress>{0}</dnatMatchSourceAddress>".format(rule['srcaddr'])
                base_payload = base_payload + src_payload 
            
            mid_payload = mid_payload + base_payload + "</natRule>"
        
        payload = start_payload + mid_payload + end_payload
        return payload

    def create_srcnat_payload(natsrc):
        '''
        From all VyOS SNAT rules, create a XML payload that can be sent to NSX
        '''
        start_payload = "<natRules>"
        end_payload = "</natRules>"
        mid_payload = ""
        for rule in natsrc.values():
            base_payload = "<natRule><action>snat</action>\
                            <originalAddress>{0}</originalAddress>\
                            <translatedAddress>{1}</translatedAddress>\
                            <loggingEnabled>false</loggingEnabled>\
                            <enabled>true</enabled>\
                            <originalPort>any</originalPort>\
                            <translatedPort>any</translatedPort>".format(rule['srcaddr'], rule['translateaddr'])
            if "description" in rule:
                descr_payload = "<description>{0}</description>".format(rule['description'])
                base_payload = base_payload + descr_payload
            if "protocol" in rule:
                if rule['protocol'] == "all":
                    proto_payload = "<protocol>any</protocol>"
                else:
                    proto_payload = "<protocol>{0}</protocol>".format(rule['protocol'])
                
            else:
                proto_payload = "<protocol>any</protocol>"
            base_payload = base_payload + proto_payload
            if "dstaddr" in rule:
                src_payload = "<snatMatchDestinationAddress>{0}</snatMatchDestinationAddress>".format(rule['dstaddr'])
                base_payload = base_payload + src_payload 
            
            mid_payload = mid_payload + base_payload + "</natRule>"
        
        payload = start_payload + mid_payload + end_payload
        return payload

    def main():
        with open("vyos.conf") as f:
            config_string = f.read()
        config = vyos.configtree.ConfigTree(config_string)

        # We start with DNAT rules
        destrulesid = config.list_nodes(["nat", "destination", "rule"])
        natdest_all = dict()
        for destruleid in destrulesid:
            '''
            We build a huge DNAT dict where keys are rules id and items are dict of rule parameter :
            '1': {'dstaddr': '1.2.3.4',
                  'outbound-interface': 'eth1',
                  'log': 'enable',
                  'protocol': 'all',
                  'translateaddr': '10.1.2.3'}
            '''
            path = ["nat", "destination", "rule {0}".format(destruleid)]
            natdest = get_nat_dest_rule(config, path)
            natdest_all[destruleid] = natdest
        #print(natdest_all)

        # Continue with SNAT rules
        srcrulesid = config.list_nodes(["nat", "source", "rule"])
        natsrc_all = dict()
        for srcruleid in srcrulesid:
            '''
            Same as the DNAT dict
            '''
            path = ["nat", "source", "rule {0}".format(srcruleid)]
            srcdest = get_nat_source_rule(config, path)
            natsrc_all[srcruleid] = srcdest
        #print(natsrc_all)

        # We now have two huge dictionnaries with DNAT and SNAT rules from VyOS
        # We are going to process them and POST them to NSX :crossed_fingers:

        # Replace edge-XXX with the right edge-id
        url = "https://{0}/api/4.0/edges/{1}/nat/config/rules".format(nsx_manager, edge_id)
        headers = {
        'Accept': 'application/xml',
        'Content-Type': 'application/xml'
        }

        dstnat_payload = create_dstnat_payload(natdest_all)
        srcnat_payload = create_srcnat_payload(natsrc_all)

        # This script is ment to be be run only once
        # Write your Vsphere login and password here
        # Don't commit your login and passord to git!!!!!!!!!
        username = 'user'
        password = 'password'
        
        # POST DNAT rules
        # This request append the rules to the existing ones
        #print(dstnat_payload)
        dstresponse = requests.request("POST", url, headers=headers, data = dstnat_payload, auth=HTTPBasicAuth(username, password), verify=False)
        print(dstresponse.headers)
        print(dstresponse.text.encode('utf8'))

        # POST SNAT rules
        # This request append the rules to the existing ones
        #print(srcnat_payload)
        srcresponse = requests.request("POST", url, headers=headers, data = srcnat_payload, auth=HTTPBasicAuth(username, password), verify=False)
        print(srcresponse.headers)
        print(srcresponse.text.encode('utf8'))

    if __name__ == '__main__':
        main()