# NASim tiny attack path

The bruteforce red participant works from the internet-reachable pivot host in
subnet one toward root ownership of both sensitive hosts.

- Own the pivot host by exploiting its reachable ssh service for user access,
  then escalate through the tomcat process to root.
- Enumerate reachable services and subnets from the owned pivot to reveal the
  two sensitive hosts.
- Exploit each sensitive host's ssh service for user access and escalate to
  root through tomcat.

The objective is met once the attacker holds root on both sensitive hosts. The
native flat action index, the raw observation vector, and per-host access-level
state stay source-private; the portable path names abstract action contracts
only.
