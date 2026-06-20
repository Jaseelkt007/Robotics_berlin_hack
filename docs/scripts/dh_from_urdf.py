#!/usr/bin/env python3
"""
Derive Denavit-Hartenberg (standard/Spong) parameters from a URDF.
Pure-Python (no numpy). Self-verifies: each extracted A_i is reconstructed
from (theta,d,a,alpha) and compared to the frame-built A_i; the max residual
is reported so we know the DH table is faithful to the URDF kinematics.

NOTE: URDFs do NOT contain DH; this derives them. Joint axes in these
CAD-exported URDFs are slightly tilted (~0.5-1 deg), so tiny residuals are
expected. The URDF remains the authoritative model for IK/FK.
"""
import sys, math, xml.etree.ElementTree as ET

# ---------- tiny linear algebra ----------
def mm(A, B):
    return [[sum(A[i][k]*B[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
def ident():
    return [[1.0 if i==j else 0.0 for j in range(4)] for i in range(4)]
def rpy_to_R(r,p,y):
    cr,sr=math.cos(r),math.sin(r); cp,sp=math.cos(p),math.sin(p); cy,sy=math.cos(y),math.sin(y)
    # URDF fixed-axis: R = Rz(y)Ry(p)Rx(r)
    return [
        [cy*cp, cy*sp*sr - sy*cr, cy*sp*cr + sy*sr],
        [sy*cp, sy*sp*sr + cy*cr, sy*sp*cr - cy*sr],
        [-sp,   cp*sr,            cp*cr]]
def T_from(xyz, rpy):
    R=rpy_to_R(*rpy); T=ident()
    for i in range(3):
        for j in range(3): T[i][j]=R[i][j]
        T[i][3]=xyz[i]
    return T
def inv(T):
    Ri=[[T[j][i] for j in range(3)] for i in range(3)]  # R^T
    t=[T[0][3],T[1][3],T[2][3]]
    ti=[-sum(Ri[i][k]*t[k] for k in range(3)) for i in range(3)]
    M=ident()
    for i in range(3):
        for j in range(3): M[i][j]=Ri[i][j]
        M[i][3]=ti[i]
    return M
def apply_dir(T,v): return [sum(T[i][j]*v[j] for j in range(3)) for i in range(3)]
def col(T,j): return [T[0][j],T[1][j],T[2][j]]
def sub(a,b): return [a[i]-b[i] for i in range(3)]
def add(a,b): return [a[i]+b[i] for i in range(3)]
def scl(a,s): return [a[i]*s for i in range(3)]
def dot(a,b): return sum(a[i]*b[i] for i in range(3))
def cross(a,b): return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
def norm(a): return math.sqrt(dot(a,a))
def unit(a):
    n=norm(a); return [a[i]/n for i in range(3)] if n>1e-12 else [0.0,0.0,0.0]

# ---------- parse URDF ----------
def parse(path):
    root=ET.parse(path).getroot()
    joints={}
    children=set()
    for j in root.findall('joint'):
        name=j.get('name'); jtype=j.get('type')
        o=j.find('origin'); xyz=[0,0,0]; rpy=[0,0,0]
        if o is not None:
            if o.get('xyz'): xyz=[float(x) for x in o.get('xyz').split()]
            if o.get('rpy'): rpy=[float(x) for x in o.get('rpy').split()]
        ax=j.find('axis'); axis=[0,0,1]
        if ax is not None and ax.get('xyz'): axis=[float(x) for x in ax.get('xyz').split()]
        parent=j.find('parent').get('link'); child=j.find('child').get('link')
        lim=j.find('limit'); lo=hi=None
        if lim is not None:
            lo=float(lim.get('lower')) if lim.get('lower') else None
            hi=float(lim.get('upper')) if lim.get('upper') else None
        joints[name]=dict(name=name,type=jtype,xyz=xyz,rpy=rpy,axis=axis,
                          parent=parent,child=child,lo=lo,hi=hi)
        children.add(child)
    # base = parent never a child
    parents=set(j['parent'] for j in joints.values())
    base=list(parents-children)[0]
    return joints, base

def chain_world(joints, base):
    """Return ordered list of revolute joints with world axis + point (home cfg)."""
    by_parent={}
    for j in joints.values(): by_parent.setdefault(j['parent'],[]).append(j)
    Tlink={base:ident()}
    order=[]
    # DFS following the longest serial path of revolute joints
    def walk(link):
        for j in by_parent.get(link,[]):
            Tc=mm(Tlink[link], T_from(j['xyz'],j['rpy']))
            Tlink[j['child']]=Tc
            if j['type']=='revolute':
                zc=unit(apply_dir(Tc,j['axis']))
                pc=[Tc[0][3],Tc[1][3],Tc[2][3]]
                order.append(dict(name=j['name'],z=zc,p=pc,lo=j['lo'],hi=j['hi']))
            walk(j['child'])
    walk(base)
    return order

# ---------- common perpendicular ----------
def feet(p0,u,p1,v):
    w0=sub(p0,p1); b=dot(u,v); d=dot(u,w0); e=dot(v,w0); den=1-b*b
    if abs(den)<1e-3:  # (near-)parallel -> avoid blow-up
        s=0.0; t=dot(sub(p0,p1),v)
    else:
        s=(b*e-d)/den; t=(e-b*d)/den
    return add(p0,scl(u,s)), add(p1,scl(v,t))

def build_frames(axes):
    n=len(axes)
    Z=[a['z'] for a in axes]; P=[a['p'] for a in axes]
    X=[None]*(n+1); O=[None]*(n+1); ZZ=[None]*(n+1)
    # frames 0..n ; frame i has z = axis of joint i+1 (Spong) -> z_i = Z[i] for i<n
    for i in range(n): ZZ[i]=Z[i]
    ZZ[n]=Z[n-1]
    # interior x_i (i=1..n-1): common normal of z_{i-1},z_i
    for i in range(1,n):
        zim1=ZZ[i-1]; zi=ZZ[i]
        c=cross(zim1,zi)
        fA,fB=feet(P[i-1],zim1,P[i],zi)
        if norm(c)>5e-2:   # treat <~3deg as parallel (CAD axes are tilted ~0.5deg)
            x=unit(sub(fB,fA))
            if norm(x)<1e-9: x=unit(c)
            O[i]=fB
        else:  # parallel
            perp=sub(sub(P[i],P[i-1]), scl(zi,dot(sub(P[i],P[i-1]),zi)))
            x=unit(perp) if norm(perp)>1e-9 else unit(cross(zi,[1,0,0]) if abs(zi[0])<0.9 else cross(zi,[0,1,0]))
            O[i]=P[i]
        X[i]=x
    # frame 0
    z0=ZZ[0]
    O[0]=sub(P[0], scl(z0, dot(P[0],z0)))   # point on axis1 nearest world origin
    if n>1 and X[1] is not None:
        x0=unit(sub(X[1], scl(z0,dot(X[1],z0))))
        if norm(x0)<1e-9: x0=X[1]
    else:
        x0=unit(cross(z0,[1,0,0]) if abs(z0[0])<0.9 else cross(z0,[0,1,0]))
    X[0]=x0
    # frame n (tool)
    zn=ZZ[n]; X[n]=X[n-1]
    O[n]=add(P[n-1], scl(zn, dot(sub(O[n-1],P[n-1]),zn)))
    # assemble T_i
    Ts=[]
    for i in range(n+1):
        z=unit(ZZ[i]); x=unit(sub(X[i], scl(z,dot(X[i],z))))  # re-orthogonalize x ⟂ z
        if norm(x)<1e-9: x=X[i]
        y=cross(z,x)
        T=ident()
        for r in range(3):
            T[r][0]=x[r]; T[r][1]=y[r]; T[r][2]=z[r]; T[r][3]=O[i][r]
        Ts.append(T)
    return Ts

def dh_params(Ts):
    rows=[]; maxres=0.0
    for i in range(1,len(Ts)):
        A=mm(inv(Ts[i-1]),Ts[i])
        theta=math.atan2(A[1][0],A[0][0])
        alpha=math.atan2(A[2][1],A[2][2])
        a=A[0][3]; d=A[2][3]
        # reconstruct to verify DH-form
        ct,st=math.cos(theta),math.sin(theta); ca,sa=math.cos(alpha),math.sin(alpha)
        R=[[ct,-st*ca,st*sa,a*ct],[st,ct*ca,-ct*sa,a*st],[0,sa,ca,d],[0,0,0,1]]
        res=max(abs(A[r][c]-R[r][c]) for r in range(4) for c in range(4))
        maxres=max(maxres,res)
        rows.append((theta,d,a,alpha,res))
    return rows, maxres

def run(path, label):
    joints, base=parse(path)
    axes=chain_world(joints, base)
    # keep only the arm chain revolute joints (drop nothing; all revolute are chain here)
    Ts=build_frames(axes)
    rows,maxres=dh_params(Ts)
    print(f"\n================  {label}  ================")
    print(f"file: {path}")
    print(f"revolute joints: {len(axes)}  ({', '.join(a['name'] for a in axes)})")
    print(f"{'i':>2} {'joint':<14} {'theta_off(rad)':>14} {'theta(deg)':>10} {'d(m)':>10} {'a(m)':>10} {'alpha(rad)':>11} {'alpha(deg)':>10} {'fit_res':>9}")
    for i,(th,d,a,al,res) in enumerate(rows):
        nm=axes[i]['name'] if i<len(axes) else 'tool'
        print(f"{i+1:>2} {nm:<14} {th:>14.5f} {math.degrees(th):>10.2f} {d:>10.5f} {a:>10.5f} {al:>11.5f} {math.degrees(al):>10.2f} {res:>9.2e}")
    print(f"max DH-form residual: {maxres:.3e}  (large on near-parallel/skew joints => DH approximate; URDF is exact)")
    # EXACT URDF kinematics (authoritative): world axis + position + relative translation
    print("\n  -- EXACT URDF kinematics (home config, base frame) --")
    print(f"  {'i':>2} {'joint':<14} {'axis (unit, world)':<34} {'position (m, world)':<30} {'Δ from prev joint (m)':<26}")
    prev=None
    for i,a in enumerate(axes):
        z=a['z']; p=a['p']
        dv=sub(p,prev) if prev is not None else p
        zs=f"({z[0]:+.4f}, {z[1]:+.4f}, {z[2]:+.4f})"
        ps=f"({p[0]:+.4f}, {p[1]:+.4f}, {p[2]:+.4f})"
        ds=f"({dv[0]:+.4f}, {dv[1]:+.4f}, {dv[2]:+.4f})"
        print(f"  {i+1:>2} {a['name']:<14} {zs:<34} {ps:<30} {ds:<26}")
        prev=p
    # joint limits
    print("limits (rad): " + ", ".join(
        f"{a['name'].split('_')[-1]}:[{a['lo']:.3f},{a['hi']:.3f}]" if a['lo'] is not None else f"{a['name']}:?"
        for a in axes))

base="/mnt/d/normacore/norma-core"
run(f"{base}/hardware/elrobot/simulation/elrobot_follower.urdf","ElRobot FOLLOWER (7-axis)")
run(f"{base}/software/station/clients/station-viewer/public/devices/so101/so101_robot_follower.urdf","SO-101 FOLLOWER")
run(f"{base}/software/station/clients/station-viewer/public/devices/so101/so101_robot_leader.urdf","SO-101 LEADER")
