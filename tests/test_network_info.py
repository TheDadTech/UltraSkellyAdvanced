from skelly_ai.network_info import summarize_network


def interfaces():
    return [dict(ifname='eth0',operstate='UP',address='02:00:00:00:00:01',addr_info=[{'local':'192.168.1.20','scope':'global'}]),
            dict(ifname='wlan0',operstate='UP',address='02:00:00:00:00:02',addr_info=[{'local':'192.168.4.1','scope':'global'}]),
            dict(ifname='lo',operstate='UNKNOWN',addr_info=[{'local':'127.0.0.1','scope':'host'}])]


def test_route_to_laptop_takes_precedence_over_internet_default():
    data=summarize_network(interfaces(),[{'dev':'eth0','gateway':'192.168.1.1'}],[{'dev':'wlan0'}])
    assert data['primary_interface']=='wlan0'
    assert data['interfaces'][0]['mac_address']=='02:00:00:00:00:02'
    assert data['interfaces'][0]['ip_addresses']==['192.168.4.1']
    assert data['gateway'] is None


def test_default_route_uses_lowest_metric_and_skips_loopback():
    data=summarize_network(interfaces(),[{'dev':'wlan0','metric':600},{'dev':'eth0','metric':100}])
    assert data['primary_interface']=='eth0' and len(data['interfaces'])==2


def test_no_default_route_keeps_active_hotspot_visible():
    data=summarize_network(interfaces(),[])
    assert data['primary_interface'] is None and len(data['interfaces'])==2
