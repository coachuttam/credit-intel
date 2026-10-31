"""The address of a client, with and without a trusted proxy (PRD SEC-15, OD-36; Phase 7 step 5)."""

import pytest

from credit_intel.api.security import client_address, parse_networks

TRUSTED = parse_networks(["172.30.60.0/24", "2001:db8::/32"])


def scope(peer, *forwarded):
    return {"client": (peer, 4000) if peer else None, "headers": [(b"x-forwarded-for", value.encode()) for value in forwarded]}


def test_without_a_trusted_proxy_the_forwarded_header_is_never_read():
    assert client_address(scope("198.51.100.7", "1.2.3.4")) == "198.51.100.7"
    assert client_address(scope("198.51.100.7", "1.2.3.4"), ()) == "198.51.100.7"


def test_a_connection_from_outside_the_trusted_network_cannot_name_itself():
    assert client_address(scope("198.51.100.7", "1.2.3.4"), TRUSTED) == "198.51.100.7"
    assert client_address(scope("172.30.61.1", "1.2.3.4"), TRUSTED) == "172.30.61.1"  # next door to the trusted network
    assert client_address(scope("2001:db9::1", "1.2.3.4"), TRUSTED) == "2001:db9::1"


def test_a_connection_from_a_trusted_proxy_is_believed_about_the_client():
    assert client_address(scope("172.30.60.10", "203.0.113.9"), TRUSTED) == "203.0.113.9"
    assert client_address(scope("2001:db8::5", "203.0.113.9"), TRUSTED) == "203.0.113.9"
    assert client_address(scope("172.30.60.10", "2001:db8:ffff::1"), TRUSTED) == "172.30.60.10"  # that client is itself inside a trusted network, so there is no untrusted address


def test_the_list_is_read_from_the_right_so_what_a_client_wrote_at_the_left_is_ignored():
    assert client_address(scope("172.30.60.10", "6.6.6.6, 203.0.113.9"), TRUSTED) == "203.0.113.9"
    assert client_address(scope("172.30.60.10", "6.6.6.6, 203.0.113.9, 172.30.60.77"), TRUSTED) == "203.0.113.9"  # a trusted hop is skipped
    assert client_address(scope("172.30.60.10", "203.0.113.9, 198.51.100.3"), TRUSTED) == "198.51.100.3"  # the nearest untrusted address is the client


def test_several_header_lines_are_read_as_one_list_in_order():
    assert client_address(scope("172.30.60.10", "6.6.6.6", "203.0.113.9"), TRUSTED) == "203.0.113.9"


@pytest.mark.parametrize("header", ["", " ", ",", "not-an-address", "203.0.113.9, nonsense", "203.0.113.9:4000", "[2001:db9::1]", "203.0.113.999", "172.30.60.1, 172.30.60.2"])
def test_a_list_that_is_empty_has_an_entry_that_is_not_an_address_or_is_all_trusted_is_not_believed(header):
    assert client_address(scope("172.30.60.10", header), TRUSTED) == "172.30.60.10"


def test_no_header_at_all_from_a_trusted_proxy_is_the_proxy_itself():
    assert client_address(scope("172.30.60.10"), TRUSTED) == "172.30.60.10"


def test_an_address_is_written_in_its_normal_form_so_two_spellings_are_one_client():
    assert client_address(scope("172.30.60.10", "2001:0db9:0000:0000:0000:0000:0000:0001"), TRUSTED) == "2001:db9::1"


def test_a_connection_with_no_client_information_is_unknown_whatever_is_trusted():
    assert client_address(scope(None, "1.2.3.4"), TRUSTED) == "unknown" and client_address(scope(None)) == "unknown"


def test_a_peer_that_is_not_an_address_is_never_trusted():
    assert client_address(scope("localhost", "1.2.3.4"), TRUSTED) == "localhost"


def test_networks_are_read_with_their_host_bits_dropped_and_a_bad_one_is_an_error():
    assert [str(n) for n in parse_networks(["10.1.2.3", "10.9.9.9/8"])] == ["10.1.2.3/32", "10.0.0.0/8"]
    with pytest.raises(ValueError):
        parse_networks(["nonsense"])
