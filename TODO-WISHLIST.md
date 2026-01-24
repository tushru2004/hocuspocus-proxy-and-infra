# Hocuspocus VPN - TODO Wishlist

## MacBook VPN Setup Requirements

### Desired Behavior
1. **VPN off by default** - When profile is installed, VPN is not automatically connected
2. **No internet without VPN** - Machine cannot connect to internet if VPN is not turned on
3. **Manual VPN activation** - User must explicitly turn on the VPN to access internet
4. **No retry loop on errors** - If VPN connection fails, it should NOT constantly try to reconnect
   - VPN should go from "off" to "on" state only
   - If connection fails, stay "off" - don't keep retrying
   - Avoid annoying reconnection loops from misconfigurations

### Technical Approach (To Research)
- **macOS Firewall Rules**: Block all outbound traffic except to VPN server IP
- **VPN On Demand (inverted)**: Configure to require VPN for all connections but not auto-connect
- **MDM Profile Options**:
  - `OnDemandEnabled` = false (don't auto-connect)
  - `DisconnectOnIdle` settings
  - Firewall payload to block non-VPN traffic

### Open Questions
- [ ] Can this be achieved with a .mobileconfig profile alone?
- [ ] Does it require MDM supervision?
- [ ] How to prevent retry loops while still blocking non-VPN traffic?
- [ ] Should we use packet filter (pf) rules instead of/in addition to VPN profile?

### Reference
- iOS iPhone setup uses Always-On VPN with `AlwaysOn` key
- macOS has different VPN profile options than iOS
- macOS firewall (pf) can be configured via MDM

---

## Other Wishlist Items

(Add future wishlist items here)
