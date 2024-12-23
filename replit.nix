
{ pkgs }: {
  deps = [
    pkgs.python313
    pkgs.python311Packages.pip
    pkgs.python311Packages.fastapi
    pkgs.python311Packages.uvicorn
    pkgs.python311Packages.motor
    pkgs.python311Packages.pydantic
    pkgs.python311Packages.python-dotenv
    pkgs.python311Packages.pymongo
    pkgs.libxcrypt
  ];
}
