import Foundation

struct AppSettings: Codable, Equatable {
    var isLoggingEnabled: Bool = false
    var preferredFontSize: FontSizePreference = .medium

    enum FontSizePreference: String, Codable, CaseIterable {
        case small = "Small"
        case medium = "Medium"
        case large = "Large"
        case extraLarge = "Extra Large"

        var pointSize: CGFloat {
            switch self {
            case .small: return 18
            case .medium: return 24
            case .large: return 32
            case .extraLarge: return 40
            }
        }
    }
}
