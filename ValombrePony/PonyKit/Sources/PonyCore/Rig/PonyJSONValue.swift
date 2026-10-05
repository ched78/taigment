import Foundation

/// Valeur JSON arbitraire, pour décoder sans échec des sections du manifeste dont la forme peut évoluer
/// (`procedural.ears`, `procedural.eyelids`, `coat`, …).
public enum PonyJSONValue: Codable, Equatable, Sendable {
    case null
    case bool(Bool)
    case number(Double)
    case string(String)
    case array([PonyJSONValue])
    case object([String: PonyJSONValue])

    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() {
            self = .null
        } else if let b = try? c.decode(Bool.self) {
            self = .bool(b)
        } else if let d = try? c.decode(Double.self) {
            self = .number(d)
        } else if let s = try? c.decode(String.self) {
            self = .string(s)
        } else if let a = try? c.decode([PonyJSONValue].self) {
            self = .array(a)
        } else if let o = try? c.decode([String: PonyJSONValue].self) {
            self = .object(o)
        } else {
            throw DecodingError.dataCorruptedError(in: c, debugDescription: "Valeur JSON non reconnue")
        }
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .null: try c.encodeNil()
        case .bool(let b): try c.encode(b)
        case .number(let d): try c.encode(d)
        case .string(let s): try c.encode(s)
        case .array(let a): try c.encode(a)
        case .object(let o): try c.encode(o)
        }
    }

    public subscript(key: String) -> PonyJSONValue? {
        if case .object(let o) = self { return o[key] }
        return nil
    }

    public var stringValue: String? {
        if case .string(let s) = self { return s }
        return nil
    }

    public var floatValue: Float? {
        if case .number(let d) = self { return Float(d) }
        return nil
    }

    public var arrayValue: [PonyJSONValue]? {
        if case .array(let a) = self { return a }
        return nil
    }

    public var objectValue: [String: PonyJSONValue]? {
        if case .object(let o) = self { return o }
        return nil
    }

    /// Première chaîne trouvée parmi plusieurs clés candidates.
    public func firstString(_ keys: [String]) -> String? {
        for k in keys {
            if let s = self[k]?.stringValue { return s }
        }
        return nil
    }

    /// Premier nombre trouvé parmi plusieurs clés candidates.
    public func firstFloat(_ keys: [String]) -> Float? {
        for k in keys {
            if let f = self[k]?.floatValue { return f }
        }
        return nil
    }
}
