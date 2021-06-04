import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit


# https://github.com/django/django/blob/main/django/utils/ipv6.py#L38
def is_valid_ipv6_address(ip_str):
    """
    Return whether or not the `ip_str` string is a valid IPv6 address.
    """
    try:
        ipaddress.IPv6Address(ip_str)
    except ValueError:
        return False
    return True


# https://github.com/django/django/blob/main/django/utils/encoding.py#L203
def punycode(domain):
    """Return the Punycode of the given domain if it's non-ASCII."""
    return domain.encode("idna").decode("ascii")


# Adapted from https://github.com/django/django/blob/main/django/core/validators.py#L65
class URLValidator:
    ul = "\u00a1-\uffff"  # Unicode letters range (must not be a raw string).

    # IP patterns
    ipv4_re = (
        r"(?:25[0-5]|2[0-4]\d|[0-1]?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|[0-1]?\d?\d)){3}"
    )
    ipv6_re = r"\[[0-9a-f:.]+\]"  # (simple regex, validated later)

    # Host patterns
    hostname_re = (
        r"[a-z" + ul + r"0-9](?:[a-z" + ul + r"0-9-]{0,61}[a-z" + ul + r"0-9])?"
    )
    # Max length for domain name labels is 63 characters per RFC 1034 sec. 3.1
    domain_re = r"(?:\.(?!-)[a-z" + ul + r"0-9-]{1,63}(?<!-))*"
    tld_re = (
        r"\."  # dot
        r"(?!-)"  # can't start with a dash
        r"(?:[a-z" + ul + "-]{2,63}"  # domain label
        r"|xn--[a-z0-9]{1,59})"  # or punycode label
        r"(?<!-)"  # can't end with a dash
        r"\.?"  # may have a trailing dot
    )
    host_re = "(" + hostname_re + domain_re + tld_re + "|localhost)"

    regex = re.compile(
        r"^(?:[a-z0-9.+-]*)://"  # scheme is validated separately
        r"(?:[^\s:@/]+(?::[^\s:@/]*)?@)?"  # user:pass authentication
        r"(?:" + ipv4_re + "|" + ipv6_re + "|" + host_re + ")"
        r"(?::\d{2,5})?"  # port
        r"(?:[/?#][^\s]*)?"  # resource path
        r"\Z",
        re.IGNORECASE,
    )
    schemes = frozenset(["http", "https", "ftp", "ftps"])
    unsafe_chars = frozenset("\t\r\n")

    def __call__(self, value: str) -> bool:
        """
        Returns True if valid URL
        """
        if not isinstance(value, str):
            return False
        if self.unsafe_chars.intersection(value):
            return False
        # Check if the scheme is valid.
        scheme = value.split("://")[0].lower()
        if scheme not in self.schemes:
            return False
        # Then check full URL
        if not self.regex.search(str(value)):
            try:
                scheme, netloc, path, query, fragment = urlsplit(value)
            except ValueError:  # for example, "Invalid IPv6 URL"
                return False
            try:
                netloc = punycode(netloc)  # IDN -> ACE
            except UnicodeError:  # invalid domain part
                return False
            url = urlunsplit((scheme, netloc, path, query, fragment))
            if not self.regex.search(str(url)):
                return False
        else:
            # Now verify IPv6 in the netloc part
            host_match = re.search(r"^\[(.+)\](?::\d{2,5})?$", urlsplit(value).netloc)
            if host_match:
                potential_ip = host_match[1]
                if not is_valid_ipv6_address(potential_ip):
                    return False

        # The maximum length of a full host name is 253 characters per RFC 1034
        # section 3.1. It's defined to be 255 bytes or less, but this includes
        # one byte for the length of the name and one byte for the trailing dot
        # that's used to indicate absolute names in DNS.
        if len(str(urlsplit(value).hostname)) > 253:
            return False
        return True


valid_url = URLValidator()
