import XCTest
@testable import pmsetly

final class ParseTests: XCTestCase {
    func testOn() {
        XCTAssertEqual(parseSleepDisabled(" hibernatemode        3\n SleepDisabled\t\t1\n sleep 0\n"), true)
    }

    func testOff() {
        XCTAssertEqual(parseSleepDisabled(" SleepDisabled\t\t0\n"), false)
    }

    func testMissing() {
        XCTAssertNil(parseSleepDisabled(" sleep                1\n"))
    }
}
