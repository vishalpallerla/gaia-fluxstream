Class FluxStream Extends %RegisteredObject
{

/// Embedded Python entry point called by RunScript.mac.
/// fluxstream is found via PYTHONPATH (set in the Dockerfile).
ClassMethod Run(inDir As %String, outPath As %String) As %Integer [ Language = python ]
{
    import fluxstream
    return fluxstream.run(inDir, outPath)
}

}
